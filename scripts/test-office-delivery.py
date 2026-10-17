"""Reproduce the upstream percent-path bug and verify the office compatibility guidance."""
import argparse
import asyncio
import json
from pathlib import Path
import tempfile
import urllib.request
import uuid
import re
import hashlib
import urllib.parse


async def direct():
    from qwenpaw.agents.tools.send_file import send_file_to_user
    with tempfile.TemporaryDirectory(prefix='office-file-delivery-') as folder:
        path=Path(folder)/'合成 #文件%20.txt'
        path.write_text('Synthetic delivery test',encoding='utf-8')
        broken=await send_file_to_user(str(path))
        assert any('does not exist' in getattr(item,'text','') for item in broken.content)
        sent=await send_file_to_user(str(path).replace('%','%25'))
        assert any(getattr(item,'type','')=='data' for item in sent.content)
        assert any('File sent successfully.' in getattr(item,'text','') for item in sent.content)
        print('PASS raw percent bug reproduced; percent-escaped tool parameter emits a real file block')


def model(path, output):
    session='office-delivery-'+uuid.uuid4().hex[:8]
    prompt=f'请交付现存合成验收文件：{path.as_posix()}。先读取当前工作区 OFFICE.md 的文件发送规范。不得改名、复制或重新生成；按规范用真实可下载链接交付，实际检查结果后再回复。测试服务基址 http://127.0.0.1:8088，智能体 default，工作区下载接口 /api/agents/default/workspace/file-download，root=workspace，path 是相对工作区的路径。不要读任何凭据或其他用户文件。'
    body={'session_id':session,'user_id':'office-synthetic-test','input':[{'role':'user','content':[{'type':'text','text':prompt}]}]}
    req=urllib.request.Request('http://127.0.0.1:8088/api/agents/default/console/chat',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    results=[]
    final=''
    with urllib.request.urlopen(req,timeout=180) as response:
        for line in response:
            if not line.startswith(b'data:'): continue
            try: event=json.loads(line[5:].decode().strip())
            except ValueError: continue
            data=event.get('data')
            if isinstance(data,dict) and str(data.get('name','')).lower() in ('sendfiletouser','send_file_to_user') and 'output' in data:
                results.append(data['output'])
            if event.get('object')=='response' and event.get('status')=='completed':
                messages=[m for m in event.get('output',[]) if m.get('role')=='assistant' and m.get('type')=='message']
                if messages: final='\n'.join(c.get('text','') for c in messages[-1].get('content',[]))
    links=re.findall(r'https?://[^\s)>\]]+',final)
    success=False
    for url in links:
        if '/workspace/file-download?' not in url: continue
        with urllib.request.urlopen(urllib.parse.quote(url,safe=':/%?=&+'),timeout=20) as response:
            data=response.read()
        success=hashlib.sha256(data).digest()==hashlib.sha256(path.read_bytes()).digest()
        if success: break
    output.mkdir(parents=True,exist_ok=True)
    (output/'delivery-model-result.json').write_text(json.dumps({'session':session,'pass':success,'tool_outputs':results,'final':final},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'session':session,'pass':success,'file_tool_outputs':len(results)}))
    assert success and not results,'Expected a working download link without the broken percent-path file tool'


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--file',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    asyncio.run(direct())
    if args.file: model(args.file.resolve(),args.output)
