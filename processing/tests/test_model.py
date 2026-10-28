"""Exercise the real subprocess HTTP adapter against a local synthetic server."""
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from tabby_processing import model


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.requests=[]
        self.status=200
        self.body={'choices':[{'finish_reason':'stop','message':{'content':'{}'}}],'model':'synthetic'}
        self.delay=0
        self.profile_reads=0
        self.switch_profile=False
        self.token_count=100
        self.bad_tokenizer=False
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_GET(self): self.do_POST()
            def do_POST(self):
                length=int(self.headers.get('Content-Length','0'))
                owner.requests.append((self.path,self.headers.get('Authorization'),self.rfile.read(length)))
                time.sleep(owner.delay)
                self.send_response(owner.status)
                self.end_headers()
                body=owner.body
                if self.path.endswith('/apply-template'):
                    body={'prompt':'synthetic formatted prompt'}
                if self.path.endswith('/tokenize'):
                    body={'tokens':[1]*owner.token_count} if not owner.bad_tokenizer else {'tokens':'bad'}
                if self.path=='/api/profiles':
                    active='gaming' if owner.switch_profile and owner.profile_reads else 'normal'
                    resolved='cpu-model' if active=='gaming' else 'gpu-model'
                    body={'active':active,'profiles':[{'id':active,'pins':{'synthetic':resolved}}]}
                    owner.profile_reads+=1
                try: self.wfile.write(json.dumps(body).encode())
                except (BrokenPipeError,ConnectionResetError): pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=self.server.serve_forever,daemon=True); thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        root=tempfile.TemporaryDirectory(); self.addCleanup(root.cleanup)
        user=Path(root.name)/'user'; user.write_text('test-user')
        password=Path(root.name)/'password'; password.write_text('test-password')
        env={'MODEL_BASE_URL':f'http://127.0.0.1:{self.server.server_port}/v1','MODEL_ALIAS':'synthetic',
             'MODEL_PROFILE':'test','MODEL_AUTH':'basic','MODEL_USERNAME_FILE':str(user),
             'MODEL_PASSWORD_FILE':str(password),'MODEL_CONTEXT_TOKENS':'16384','MODEL_OUTPUT_TOKENS':'2048'}
        env['MODEL_BACKEND']='openai-compatible'
        env['MODEL_THINKING']='false'
        env['MODEL_SOCKET_TIMEOUT_SECONDS']='1140'
        self.env=patch.dict(os.environ,env); self.env.start(); self.addCleanup(self.env.stop)

    def test_basic_auth_structured_request_and_metadata(self):
        value=model.call('synthetic email',timeout=5)
        path,auth,body=self.requests[0]
        self.assertEqual(path,'/v1/chat/completions')
        self.assertEqual(auth,'Basic '+base64.b64encode(b'test-user:test-password').decode())
        payload=json.loads(body)
        self.assertEqual(payload['response_format']['type'],'json_schema')
        self.assertFalse(payload['chat_template_kwargs']['enable_thinking'])
        self.assertEqual(value['metadata']['prompt_hash'],model.PROMPT_HASH)
        self.assertNotIn('password',json.dumps(value))

    def test_models_and_selected_alias(self):
        self.body={'data':[{'id':'synthetic'}]}
        self.assertTrue(model.call(action='models',timeout=5)['selected_available'])
        self.assertEqual(self.requests[0][0],'/v1/models')

    def test_statuses_no_redirect_or_response_leak(self):
        self.body={'secret':'must-not-leak'}
        for status,transient in ((429,True),(503,True),(401,False),(302,False)):
            self.status=status
            with self.subTest(status=status),self.assertRaises(model.ModelError) as raised: model.call(timeout=5)
            self.assertEqual(raised.exception.transient,transient)
            self.assertNotIn('must-not-leak',str(raised.exception))
        self.assertEqual(len(self.requests),4)

    def test_protocol_and_output_limits(self):
        for body in ({'choices':[]},{'choices':[{'finish_reason':'length','message':{'content':'{}'}}]}, {'x':'x'*140000}):
            self.body=body
            with self.assertRaises(model.ModelError): model.call(timeout=5)

    def test_deadline_kills_child(self):
        self.delay=2
        started=time.monotonic()
        with self.assertRaises(model.ModelError) as raised: model.call(timeout=0.2)
        self.assertEqual(raised.exception.code,'model_deadline')
        self.assertLess(time.monotonic()-started,1.5)

    def test_invalid_unicode_and_nul_are_reviewable_protocol_errors(self):
        for raw in ('\x00','\ud800'):
            self.body={'choices':[{'finish_reason':'stop','message':{'content':raw}}]}
            with self.assertRaises(model.ModelError) as raised: model.call(timeout=5)
            self.assertEqual(raised.exception.code,'model_response_invalid')

    def test_input_budget_and_endpoint_identity(self):
        settings=model.config()
        model.payload(settings,'short synthetic bank email')
        with self.assertRaises(model.ModelError): model.payload(settings,'x'*24000)
        with patch.dict(os.environ,MODEL_ALIAS='other'):
            self.assertNotEqual(model.config()['identity'],settings['identity'])
        with patch.dict(os.environ,MODEL_BASE_URL='http://private.example/v1'):
            with self.assertRaises(model.ModelError): model.config()

    def test_llama_swap_observations_do_not_claim_weight_identity(self):
        with patch.dict(os.environ,MODEL_BACKEND='llama-swap',MODEL_CONTEXT_TOKENS='8192'):
            result=model.call('synthetic',timeout=5)
        metadata=result['metadata']
        self.assertEqual(metadata['routing_before'],{'active':'normal','resolved_model':'gpu-model'})
        self.assertTrue(metadata['routing_observed_stable'])
        self.assertFalse(metadata['weights_verified'])
        self.assertEqual([r[0] for r in self.requests],['/api/profiles','/upstream/synthetic/apply-template',
                         '/upstream/synthetic/tokenize','/api/profiles','/v1/chat/completions','/api/profiles'])

    def test_profile_switch_and_context_ceiling(self):
        self.switch_profile=True
        with patch.dict(os.environ,MODEL_BACKEND='llama-swap',MODEL_CONTEXT_TOKENS='8192'):
            with self.assertRaises(model.ModelError) as raised: model.call('synthetic',timeout=5)
            self.assertEqual(raised.exception.code,'model_profile_changed')
            self.assertTrue(raised.exception.transient)
            self.assertNotIn('/v1/chat/completions',[r[0] for r in self.requests])
            with patch.dict(os.environ,MODEL_CONTEXT_TOKENS='32768'):
                with self.assertRaises(model.ModelError): model.config()

    def test_cold_start_socket_timeout_configuration(self):
        self.assertEqual(model.config()['socket_timeout'],1140)
        with patch.dict(os.environ,MODEL_SOCKET_TIMEOUT_SECONDS='0'):
            with self.assertRaises(model.ModelError): model.config()

    def test_thinking_budget_and_usage_without_reasoning_storage(self):
        self.body['choices'][0]['message']['reasoning_content']='private reasoning must not persist'
        self.body['usage']={'prompt_tokens':100,'completion_tokens':200,'total_tokens':300,'secret':'hidden'}
        with patch.dict(os.environ,MODEL_BACKEND='llama-swap',MODEL_CONTEXT_TOKENS='8192',MODEL_THINKING='true',MODEL_OUTPUT_TOKENS='4096'):
            result=model.call('synthetic',timeout=5)
        self.assertTrue(result['metadata']['thinking'])
        self.assertTrue(result['metadata']['reasoning_returned'])
        self.assertEqual(result['metadata']['budget']['input_tokens'],100)
        self.assertEqual(result['metadata']['usage'],{'prompt_tokens':100,'completion_tokens':200,'total_tokens':300})
        self.assertNotIn('private reasoning',json.dumps(result))
        body=json.loads(next(r[2] for r in self.requests if r[0]=='/v1/chat/completions'))
        self.assertEqual(body['max_tokens'],4096)
        self.assertTrue(body['chat_template_kwargs']['enable_thinking'])

    def test_context_budget_exhaustion_prevents_generation(self):
        self.token_count=3585
        with patch.dict(os.environ,MODEL_BACKEND='llama-swap',MODEL_CONTEXT_TOKENS='8192',MODEL_OUTPUT_TOKENS='4096'):
            with self.assertRaises(model.ModelError) as raised: model.call('synthetic',timeout=5)
        self.assertEqual(raised.exception.code,'model_input_budget')
        self.assertNotIn('/v1/chat/completions',[r[0] for r in self.requests])

    def test_tokenizer_failure_is_not_silently_estimated(self):
        self.bad_tokenizer=True
        with patch.dict(os.environ,MODEL_BACKEND='llama-swap',MODEL_CONTEXT_TOKENS='8192'):
            with self.assertRaises(model.ModelError) as raised: model.call('synthetic',timeout=5)
        self.assertEqual(raised.exception.code,'model_tokenizer_response_invalid')

    def test_thinking_setting_changes_identity(self):
        old=model.config()['identity']
        with patch.dict(os.environ,MODEL_THINKING='true'):
            self.assertNotEqual(old,model.config()['identity'])
        with patch.dict(os.environ,MODEL_THINKING='yes'):
            with self.assertRaises(model.ModelError): model.config()

    def test_temperature_is_bounded_and_changes_identity(self):
        old=model.config()['identity']
        with patch.dict(os.environ,MODEL_TEMPERATURE='0'):
            self.assertEqual(model.config()['temperature'],0)
            self.assertNotEqual(old,model.config()['identity'])
        for value in ('nan','inf','-1','3','invalid'):
            with self.subTest(value=value),patch.dict(os.environ,MODEL_TEMPERATURE=value):
                with self.assertRaises(model.ModelError): model.config()

    def test_adaptive_output_keeps_minimum_and_reserve(self):
        self.token_count=2000
        with patch.dict(os.environ,MODEL_BACKEND='llama-swap',MODEL_CONTEXT_TOKENS='8192',
                        MODEL_OUTPUT_TOKENS='6144',MODEL_MIN_OUTPUT_TOKENS='4096'):
            result=model.call('synthetic',timeout=5)
        body=json.loads(next(r[2] for r in self.requests if r[0]=='/v1/chat/completions'))
        self.assertEqual(body['max_tokens'],5680)

    def test_exhaustion_preserves_safe_budget_metadata(self):
        self.body['choices'][0]['finish_reason']='length'
        self.body['choices'][0]['message']['reasoning_content']='private'
        with patch.dict(os.environ,MODEL_BACKEND='llama-swap',MODEL_CONTEXT_TOKENS='8192'):
            with self.assertRaises(model.ModelError) as raised:
                model.call('synthetic',timeout=5)
        self.assertEqual(raised.exception.code,'model_output_incomplete')
        self.assertIn('budget',raised.exception.metadata)
        self.assertNotIn('private',json.dumps(raised.exception.metadata))

