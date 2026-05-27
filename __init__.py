# -*- coding: UTF-8 -*-
"""
作者艾琳有栖
版本 0.0.8
基于 nonebot 问答
"""
import re
import random
from nonebot import *
from . import util
from .util import make_forward_msg  # 新增这行
from hoshino import Service, priv  # 如果使用hoshino的分群管理取消注释这行
from . import web_api  # 注册 HTTP API 路由
#
sv_help = '''
- [有人/大家说AA回答BB] 对所有人生效
- [我说AA回答BB] 仅仅对个人生效
- [不要回答AA] 删除某问题下的回答(优先度:自己设置的>最后设置的)
- [问答] 查看自己的回答,@别人可以看别人的
- [全部问答] 查看本群设置的回答
- 只有管理可以删别人设置的哦~~~
※进阶用法：
发送[epa进阶用法]可查看
'''.strip()
sv_help1 = '''
- [有人/大家说AA回答=BB] 
- [我说AA回答=BB] 
对于bot而言你说AA就是在说BB
示例：
我说1回答=xcwkkp 
或者
我说1回答=echo CQ码
CQ码部分
- [CQ码帮助]
'''.strip()

sv = Service(
    name = '问答',  #功能名
    use_priv = priv.NORMAL, #使用权限   
    manage_priv = priv.ADMIN, #管理权限
    visible = True, #False隐藏
    enable_on_default = True, #是否默认启用
    bundle = '通用', #属于哪一类
    help_ = sv_help #帮助文本
    )

@sv.on_fullmatch(["帮助问答"])
async def bangzhu(bot, ev):
    await bot.send(ev, sv_help, at_sender=True)
    
@sv.on_fullmatch(["epa进阶用法"])
async def bangzhu(bot, ev):
    await bot.send(ev, sv_help1)
    
config = util.get_config()
db = util.init_db(config['cache_dir'])

_bot = get_bot()

admins = config['admins']
admins = set((admins if isinstance(admins, list) else [admins]) + _bot.config.SUPERUSERS)


@sv.on_message('group')  # 如果使用hoshino的分群管理取消注释这行 并注释下一行的 @_bot.on_message("group")
# @_bot.on_message("group") # nonebot使用这
async def eqa_main(*params):
    bot, ctx = (_bot, params[0]) if len(params) == 1 else params

    msg = str(ctx['message']).strip()

    # 处理回答所有人的问题
    keyword = util.get_msg_keyword(config['comm']['answer_all'], msg, True)
    if keyword:
        msg = await ask(ctx, keyword, False)
        if msg:
            # 普通文本回复（设置问答成功提示）
            return await bot.send(ctx, msg)

    # 处理回答自己的问题
    keyword = util.get_msg_keyword(config['comm']['answer_me'], msg, True)
    if keyword:
        msg = await ask(ctx, keyword, True)
        if msg:
            # 普通文本回复（设置问答成功提示）
            return await bot.send(ctx, msg)

    # 回复消息（合并转发）
    ans = await answer(ctx)
    if isinstance(ans, list):  
        try:  
            return await make_forward_msg(bot, ctx, ans, title="问答回复", brief="查看问答回复内容")  
        except Exception:  
            # Fallback to normal sending  
            content = ans[0]['content'] if ans else ''  
            return await bot.send(ctx, content)

    # 显示全部设置的问题（合并转发）
    show_target = util.get_msg_keyword(config['comm']['show_question_list'], msg, True)
    if isinstance(show_target, str):
        forward_list = await show_question(ctx, show_target, True)
        return await make_forward_msg(bot, ctx, forward_list, title="全部问答列表", brief="查看本群所有问答")

    # 显示设置的问题（合并转发）
    show_target = util.get_msg_keyword(config['comm']['show_question'], msg, True)
    if isinstance(show_target, str):
        forward_list = await show_question(ctx, show_target)
        return await make_forward_msg(bot, ctx, forward_list, title="个人问答列表", brief="查看个人问答")

    # 删除设置的问题（普通文本回复）
    del_target = util.get_msg_keyword(config['comm']['answer_delete'], msg, True)
    if del_target:
        del_msg = await del_question(ctx, del_target)
        return await bot.send(ctx, del_msg)

    # 清空设置的问题（普通文本回复）
    del_all = util.get_msg_keyword(config['comm']['answer_delete_all'], msg, True)
    if del_all:
        del_msg = await del_question(ctx, del_all, True)
        return await bot.send(ctx, del_msg)


# 设置问题的函数
async def ask(ctx, keyword, is_me):
    is_super_admin = ctx['user_id'] in admins
    is_admin = util.is_group_admin(ctx) or is_super_admin

    if config['rule']['only_admin_answer_all'] and not is_me and not is_admin:
        return '回答所有人的只能管理设置啦'

    question_handler = config['comm']['answer_me'] if is_me else config['comm']['answer_all']
    answer_handler = config['comm']['answer_handler']
    qa_msg = util.get_msg_keyword(answer_handler, keyword)
    if not qa_msg:
        return False
    ans, qus = qa_msg
    qus = f'{qus}'.strip()
    if not str(qus).strip():
        return '问题呢? 问题呢??'
    if not str(ans).strip():
        return '回答呢? 回答呢??'

    # 关键修改：拆分多个问题（以/分隔）
    qus_list_split = [q.strip() for q in qus.split('/') if q.strip()]
    if not qus_list_split:
        return '问题格式错误，不能只输入/哦~'

    # 问题与回答的分割
    ans_start = util.find_ms_str_index(ctx['message'], answer_handler)

    if re.search(r'\[CQ:image,', qus):
        qus = util.get_message_str(ctx['message'][:ans_start])
        qus = util.get_msg_keyword(question_handler, qus, True).strip()
        # 重新拆分带图片的多问题
        qus_list_split = [q.strip() for q in qus.split('/') if q.strip()]

    message = []
    _once = False
    for ms in ctx['message'][ans_start:]:
        if ms['type'] == 'text':
            reg = util.get_msg_keyword(answer_handler, ms['data']['text'])
            if reg and not _once:
                _once = True
                ms = MessageSegment.text(reg[0])
        if ms['type'] == 'image':
            ms = util.ms_handler_image(ms, config['rule']['use_cq_code_image_url'], config['cache_dir'],
                                       b64=config['image_base64'])
            if not ms:
                return '图片缓存失败了啦！'
        message.append(ms)

    # 为每个拆分后的问题单独存储
    success_count = 0
    for single_qus in qus_list_split:
        qus_list = db.get(single_qus, [])
        qus_list.append({
            'user_id': ctx['user_id'],
            'group_id': ctx['group_id'],
            'is_me': is_me,
            'qus': single_qus,
            'message': message
        })
        db[single_qus] = qus_list
        success_count += 1

    return f'我学会啦！共设置了{success_count}个问题，来问问我吧～'


# 回复的函数
async def answer(ctx):
    msg = util.get_message_str(ctx['message']).strip()
    ans_list = db.get(msg, [])
    if not ans_list:
        return False

    group_id = ctx['group_id']
    user_id = ctx['user_id']
    super_admin_is_all_group = config['rule']['super_admin_is_all_group']
    priority_self_answer = config['rule']['priority_self_answer']
    multiple_question_random_answer = config['rule']['multiple_question_random_answer']

    # 获取到当前群的列表 判断是否来自该群 或者是否是超级管理员
    ans_list = util.filter_list(ans_list, lambda x: group_id == x['group_id'] or (
            x['user_id'] in admins if super_admin_is_all_group else False))

    if not ans_list:
        return False

    # 是否优先自己的回答
    if priority_self_answer:
        self_list = util.filter_list(ans_list, lambda x: user_id == x['user_id'])
        ans_list = self_list if self_list else ans_list

    # 随机/最后一个回复
    if multiple_question_random_answer:
        ans = random.choice(ans_list)
    else:
        ans = ans_list[-1]

    # 验证是否是个人专属回复
    if ans['is_me'] and ans['user_id'] != user_id:
        return False

    # 处理命令前缀（原逻辑保留）
    msg_content = ans['message']
    if len(msg_content) == 1:
        _msg = msg_content[0]
        if _msg['type'] == 'text' and _msg['data']['text'][:1] == config['str']['cmd_head_str']:
            ctx['raw_message'] = _msg['data']['text'][1:]
            ctx['message'] = Message(ctx['raw_message'])
            _bot.on_message(ctx)
            return False

    # 处理base64图片（原逻辑保留）
    if config['image_base64']:
        msg_content = util.message_image2base64(msg_content)
    
    # 新增：处理链接防拦截  
    processed_content = []  
    for ms in msg_content:  
        if ms['type'] == 'text':  
            # 对文本内容中的链接进行处理  
            processed_text = util.process_url_with_break(ms['data']['text'])  
            processed_content.append(MessageSegment.text(processed_text))  
        else:  
            processed_content.append(ms)  
    msg_content = processed_content  
    
    # 构造合并转发消息（核心修改）
    forward_msg_list = [{
        "name": "问答机器人",  # 转发卡片中显示的发送者名
        "uin": ctx['self_id'],  # 机器人QQ
        "content": msg_content  # 问答内容
    }]
    return forward_msg_list  # 返回转发消息列表，交给外层处理


# 显示问题的函数
async def show_question(ctx, target, show_all=False):
    print_all_split = config['str']['print_all_split'] or " | "

    db_list = list(db.values())
    ans_list = util.get_current_ans_list(ctx, db_list)

    if not show_all:
        is_super_admin = ctx['user_id'] in admins
        is_admin = util.is_group_admin(ctx) or is_super_admin

        target = list(int(i) for i in re.findall(r'\[CQ:at,qq=(\d+)]', target.strip()))
        is_at = bool(target)

        if not config['rule']['member_can_show_other'] and target and not is_admin:
            # 改为返回转发消息格式
            return [{
                "name": "问答机器人",
                "uin": ctx['self_id'],
                "content": '不能看别人设置的问题啦'
            }]

        target = target if is_at else [ctx['user_id']]
    else:
        target = [ctx['user_id']]
        is_at = False

    forward_msg_list = []  # 合并转发消息列表
    for qq in target:
        head = ''
        priority_list = []
        if not show_all:
            if qq in admins:
                ans_list = util.get_all_ans_list_by_qq(qq, db_list)
            else:
                ans_list = util.get_all_ans_list_by_qq(qq, ans_list)
        else:
            all_list = util.filter_list(ans_list, lambda x: True in list(not i['is_me'] for i in x))
            priority_list = util.filter_list(ans_list, lambda x: True in list(i['is_me'] for i in x))
            ans_list = sum(list(util.get_all_ans_list_by_qq(q, db_list) for q in admins), all_list)

        # 处理发送者名称
        if is_at:
            name = await util.get_group_member_name(ctx['group_id'], qq)
            head = f'{name} :\n'
        else:
            name = "问答机器人"

        # 拼接问答内容
        str_list = util.get_qus_str_by_list(ans_list)
        str_list = await util.cq_msg2str(str_list, group_id=ctx['group_id'])
        msg_context = f'全体问答:\n{print_all_split.join(str_list)}' if show_all else "/".join(str_list)

        priority_msg = ''
        if show_all:
            pri_str_list = util.get_qus_str_by_list(priority_list)
            pri_str_list = await util.cq_msg2str(pri_str_list, group_id=ctx['group_id'])
            priority_msg = "\n个人问答:\n" + print_all_split.join(pri_str_list)

        final_content = f"{head}{msg_context if ans_list else '还没有设置过问题呢'}{priority_msg}"
        # 添加到转发列表
        forward_msg_list.append({
            "name": name,
            "uin": qq if is_at else ctx['self_id'],
            "content": final_content
        })

    return forward_msg_list  # 返回转发消息列表


# 删除问题的函数
async def del_question(ctx, target, clear=False):
    target = util.get_message_str(target).strip()
    # 关键修改：拆分多个要删除的问题
    target_list = [t.strip() for t in target.split('/') if t.strip()]
    if not target_list:
        return '没这个问题哦'

    is_super_admin = ctx['user_id'] in admins
    is_group_admin = util.is_group_admin(ctx) if config['rule']['only_admin_can_delete'] else True
    is_admin = is_group_admin or is_super_admin

    # 如果直接清空
    if clear:
        if is_super_admin:
            del_count = 0
            for t in target_list:
                ans_list = db.get(t, [])
                if ans_list:
                    util.delete_message_image_file(ans_list)
                    db.pop(t)
                    del_count += 1
            return f'清空成功~ 共删除{del_count}个问题'
        else:
            return '木有权限啦~~'

    del_count = 0
    for t in target_list:
        ans_list = db.get(t, [])
        if not ans_list:
            continue

        if config['rule']['question_del_last']:
            ans_list.reverse()

        is_del_flag = False
        for index, value in enumerate(ans_list):
            # 如果不是本群就跳过  或者 是超级管理员的话 就继续删除
            if value['group_id'] != ctx['group_id'] and not (is_super_admin and value['user_id'] in admins):
                continue
            # 管理员则直接删除第一个元素
            if is_admin:
                if not config['rule']['can_delete_super_admin_qa'] and \
                        value['user_id'] in admins and \
                        not is_super_admin:
                    continue
                else:
                    is_del_flag = True
                    util.delete_message_image_file(value)
                    ans_list.pop(index)
                    break
            else:
                # 如果不是管理员 就删除自己的第一个元素
                if value['user_id'] == ctx['user_id']:
                    is_del_flag = True
                    util.delete_message_image_file(value)
                    ans_list.pop(index)
                    break

        if is_del_flag:
            if config['rule']['question_del_last']:
                ans_list.reverse()
            if bool(ans_list):
                db[t] = ans_list
            else:
                db.pop(t)
            del_count += 1

    return f'删除成功啦！共删除{del_count}个问题' if del_count > 0 else '删除失败 可能木有权限'

    # 表示删除了元素 可以更新数据库了
    if is_del_flag:
        # 如果刚刚反转了 那要反转回来
        if config['rule']['question_del_last']:
            ans_list.reverse()
        if bool(ans_list):
            db[target] = ans_list
        else:
            db.pop(target)

    return '删除成功啦' if is_del_flag else '删除失败 可能木有权限'