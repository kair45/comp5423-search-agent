"""Transport-contract regression tests with no external requests or real keys."""
import os
import unittest
from unittest.mock import Mock, patch

from searchkit.provider import Provider

class ServiceTests(unittest.TestCase):
    def test_provider_specific_requests(self):
        for name,key,model,url in [
            ("siliconflow","SILICONFLOW_API_KEY","deepseek-ai/DeepSeek-V4-Flash","https://api.siliconflow.cn/v1"),
            ("aliyun","DASHSCOPE_API_KEY","deepseek-v4-flash-0731","https://ws-local.cn-beijing.maas.aliyuncs.com/compatible-mode/v1")]:
            with self.subTest(service=name),patch.dict(os.environ,{"LLM_PROVIDER":name,key:"local-test-value","DASHSCOPE_WORKSPACE_ID":"ws-local","DASHSCOPE_REGION":"cn-beijing"},clear=True):
                p=Provider(); response=Mock(ok=True,is_redirect=False,status_code=200)
                response.json.return_value={"model":model,"id":"local","choices":[{"finish_reason":"stop","message":{"role":"assistant","content":"Sample"}}],"usage":{"total_tokens":12}}
                p.http.post=Mock(return_value=response)
                msg,usage,meta=p.complete([{"role":"user","content":"example"}],[])
                self.assertEqual((msg["content"],usage["total_tokens"],meta["model"]),("Sample",12,model))
                args,kwargs=p.http.post.call_args;self.assertEqual(args,(url+"/chat/completions",))
                self.assertFalse(kwargs["allow_redirects"]);self.assertFalse(kwargs["json"]["enable_thinking"])
                self.assertEqual(kwargs["json"]["model"],model)
                response.json.return_value["model"]="deepseek-v4.1-flash"
                with self.assertRaises(ValueError):p.complete([],[])
    def test_unsupported_service_stops_before_http(self):
        with patch.dict(os.environ,{"LLM_PROVIDER":"unconfigured"},clear=True):
            with self.assertRaisesRegex(ValueError,"siliconflow or aliyun"):Provider()
if __name__=="__main__":unittest.main()
