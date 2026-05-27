# -*- coding: UTF-8 -*-  
"""  
EQA 问答 HTTP API  
只调取群号 428682530 的问答，支持图片  
"""  
import asyncio  
import json  
import os  
import base64  
from urllib.parse import unquote  
from aiohttp import web  
from . import util  
  
config = util.get_config()  
db = util.init_db(config['cache_dir'])  
  
EQA_API_PORT = 8067  
TARGET_GROUP_ID = 428682530  
  
# 基于插件目录计算绝对路径，确保无论工作目录在哪都能找到图片  
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))  
IMG_DIR = os.path.join(PLUGIN_DIR, 'data', 'img')  
  
routes = web.RouteTableDef()  
  
  
@routes.get('/eqa/api/questions')  
async def eqa_questions(request):  
    """获取群 428682530 的所有公开问题列表"""  
    questions = []  
    for key in db.keys():  
        ans_list = db[key]  
        group_answers = [a for a in ans_list  
                         if a['group_id'] == TARGET_GROUP_ID and not a['is_me']]  
        if group_answers:  
            questions.append({  
                "question": key,  
                "answer_count": len(group_answers)  
            })  
    return web.json_response(  
        {"questions": questions},  
        dumps=lambda x: json.dumps(x, ensure_ascii=False)  
    )  
  
  
@routes.get('/eqa/api/answer')  
async def eqa_answer(request):  
    """获取某问题的所有回答（仅群 428682530），返回结构化内容（文本+图片）"""  
    question = unquote(request.query.get('question', ''))  
    ans_list = db.get(question, [])  
    answers = []  
    for a in ans_list:  
        if a['group_id'] != TARGET_GROUP_ID:  
            continue  
        segments = []  
        for ms in a['message']:  
            if ms['type'] == 'text':  
                text = ms['data'].get('text', '')  
                if text.strip():  
                    segments.append({"type": "text", "data": text})  
            elif ms['type'] == 'image':  
                # 优先用 url 字段（go-cqhttp 通常保存了 CDN 地址）  
                url = ms['data'].get('url', '')  
                file_ref = ms['data'].get('file', '')  
  
                if url and url.startswith('http'):  
                    # 有 CDN URL，直接用  
                    segments.append({"type": "image", "data": url})  
                elif file_ref:  
                    if file_ref.startswith('base64://'):  
                        segments.append({"type": "image", "data": file_ref})  
                    else:  
                        # 本地文件引用：提取文件名，通过 /eqa/api/image 提供  
                        fname = os.path.basename(file_ref)  
                        segments.append({  
                            "type": "image",  
                            "data": f"/eqa/api/image?file={fname}"  
                        })  
        answers.append({  
            "user_id": a['user_id'],  
            "is_me": a['is_me'],  
            "segments": segments  
        })  
    return web.json_response(  
        {"question": question, "answers": answers},  
        dumps=lambda x: json.dumps(x, ensure_ascii=False)  
    )  
  
  
@routes.get('/eqa/api/image')  
async def eqa_image(request):  
    """提供本地图片文件的 HTTP 访问"""  
    fname = request.query.get('file', '')  
    if not fname or '..' in fname:  
        return web.Response(status=400, text='Invalid file name')  
  
    base_name = os.path.splitext(fname)[0]  
    target = None  
    if os.path.isdir(IMG_DIR):  
        for f in os.listdir(IMG_DIR):  
            if os.path.splitext(f)[0] == base_name:  
                target = os.path.join(IMG_DIR, f)  
                break  
  
    if not target or not os.path.isfile(target):  
        return web.Response(status=404, text=f'Image not found: {fname}')  
  
    file_size = os.path.getsize(target)  
    ext = os.path.splitext(target)[-1].lower()  
  
  
    # 原图返回  
    content_types = {  
        '.png': 'image/png', '.jpg': 'image/jpeg',  
        '.jpeg': 'image/jpeg', '.gif': 'image/gif',  
        '.webp': 'image/webp',  
    }  
    ct = content_types.get(ext, 'application/octet-stream')  
    with open(target, 'rb') as f:  
        data = f.read()  
    return web.Response(body=data, content_type=ct)
  
  
@routes.get('/eqa/api/debug')  
async def eqa_debug(request):  
    """调试端点：查看数据库中某问题的原始数据"""  
    question = unquote(request.query.get('question', ''))  
    info = {  
        "plugin_dir": PLUGIN_DIR,  
        "img_dir": IMG_DIR,  
        "img_dir_exists": os.path.isdir(IMG_DIR),  
        "img_files_sample": [],  
        "question": question,  
        "raw_data": []  
    }  
    # 列出 img 目录前 20 个文件  
    if os.path.isdir(IMG_DIR):  
        files = os.listdir(IMG_DIR)  
        info["img_files_count"] = len(files)  
        info["img_files_sample"] = files[:20]  
  
    if question:  
        ans_list = db.get(question, [])  
        for a in ans_list:  
            if a['group_id'] == TARGET_GROUP_ID:  
                info["raw_data"].append({  
                    "user_id": a['user_id'],  
                    "is_me": a['is_me'],  
                    "message": a['message']  
                })  
    else:  
        # 没指定问题时，列出所有问题  
        all_q = []  
        for key in db.keys():  
            ans_list = db[key]  
            group_answers = [a for a in ans_list if a['group_id'] == TARGET_GROUP_ID]  
            if group_answers:  
                all_q.append(key)  
        info["all_questions"] = all_q  
  
    return web.json_response(  
        info,  
        dumps=lambda x: json.dumps(x, ensure_ascii=False, default=str)  
    )  
  
  
async def start_eqa_web():  
    """启动 EQA HTTP API 服务器"""  
    app = web.Application()  
    app.add_routes(routes)  
    runner = web.AppRunner(app)  
    await runner.setup()  
    site = web.TCPSite(runner, '0.0.0.0', EQA_API_PORT)  
    await site.start()  
    print(f'[EQA] HTTP API 已启动，监听端口 {EQA_API_PORT}，仅提供群 {TARGET_GROUP_ID} 的问答')  
    print(f'[EQA] 插件目录: {PLUGIN_DIR}')  
    print(f'[EQA] 图片目录: {IMG_DIR} (存在: {os.path.isdir(IMG_DIR)})')  
  
  
asyncio.get_event_loop().create_task(start_eqa_web())