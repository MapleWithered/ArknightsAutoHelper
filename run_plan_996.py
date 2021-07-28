from Arknights.helper import logger
from Arknights.shell_next import _create_helper
from addons.activity import get_stage
import config
import json
import os
import time
import datetime

import schedule

list_not_open = []

def run_plan():

    helper, _ = _create_helper()
    
    assert os.path.exists('user_file/plan.json'), '未能检测到刷图计划文件.'

    with open('user_file/plan.json', 'r', encoding='utf-8') as f:
        plan = json.load(f)

    assert plan['stages'], "刷图计划文件中未能检测到刷图计划，或格式错误"

    logger.warning('开始刷图')

    has_remain_sanity = True

    while has_remain_sanity:
        priority_id = 0
        for priority in plan['stages']:
            priority_id += 1
            stages_same_prior = priority['stages']
            # 找出符合要求的关卡：余比最高的开放关卡
            stage_ok_id = -1
            max_remain_ratio = 0
            for i in range(len(stages_same_prior)):
                stage = stages_same_prior[i]
                remain_ratio = stage.get('remain', stage['count']) / stage['count']
                if stage['stage'] not in list_not_open and stage.get('remain', stage['count']) > 0 and remain_ratio > max_remain_ratio:
                    stage_ok_id = i
                    max_remain_ratio = remain_ratio
            if stage_ok_id == -1:
                logger.warning('优先级 ' + str(priority_id) + ' 无剩余未完成开放关卡')
                continue # 没有未完成的开放关卡，下一优先级
            stage = stages_same_prior[stage_ok_id]
            remain = stage.get('remain', stage['count'])
            logger.warning('优先级: %s, 关卡 [%s], 总计划: %s, 剩余次数: %s, 备注: %s' % (priority_id, stage['stage'], stage['count'], remain, stage['//']))
            try:
                # 执行未完成的开放关卡一次
                c_id, remain = helper.module_battle(stage['stage'], 1)
            except RuntimeError:
                # 未开放，加入未开放关卡列表中
                logger.info('关卡 [%s] 未开放, 继续下一关卡' % stage['stage'])
                list_not_open.append(stage['stage'])
                logger.info('当日未开放关卡列表：' + str(list_not_open))
                break # 重新进行优先级遍历
            except ValueError:
                # 非主线芯片关卡（即，故事集/活动/剿灭）
                helper.back_to_main()
                # 得到关卡前缀
                if stage['stage'].rfind('-') == -1:
                    stage_category = stage['stage']
                else:
                    stage_category = stage['stage'][:stage['stage'].rfind('-')]
                record_name = f"main_to_{stage_category}"
                # 判断点击路径是否存在
                if not os.path.exists(f'custom_record/{record_name}/record.json'):
                    # 不存在点击路径 进行录制
                    logger.warning(f"当前关卡{stage_category}，未录制点击路径。")
                    c = input(f'是否录制相应操作记录(需要 MuMu 模拟器)[y/N]:').strip().lower()
                    if c != 'y':
                        # 用户不希望录制 当日内忽略此关卡
                        list_not_open.append(stage['stage'])
                        logger.info(f"今日将忽略 {stage['stage']} 关卡")
                        break # 重新进行优先级遍历
                    # 希望录制 判断支线关卡/剿灭作战
                    if stage['stage'].find('-') != -1:
                        # 支线活动关卡
                        wait_seconds_after_touch = 2
                        print('录制到进入活动关卡选择界面即可, 无需点击具体的某个关卡.')
                        print(f'如果需要重新录制, 删除 custom_record 下的 {record_name} 文件夹即可.')
                        print(f'请在点击后等待 {wait_seconds_after_touch} s , 待控制台出现 "继续..." 字样, 再进行下一次点击.')
                        print(f'请在点击后等待 {wait_seconds_after_touch} s , 待控制台出现 "继续..." 字样, 再进行下一次点击.')
                        print(f'请在点击后等待 {wait_seconds_after_touch} s , 待控制台出现 "继续..." 字样, 再进行下一次点击.')
                        print(f'准备开始录制 {record_name}...')
                        helper.create_custom_record(record_name, roi_size=64,
                                                        description=f"从主线一路点击进入{stage_category}关卡（章节）",
                                                        wait_seconds_after_touch=wait_seconds_after_touch)
                    else:
                        # 剿灭作战
                        wait_seconds_after_touch = 2
                        print('录制到出现开始行动按钮为止。')
                        print(f'如果需要重新录制, 删除 custom_record 下的 {record_name} 文件夹即可.')
                        print(f'请在点击后等待 {wait_seconds_after_touch} s , 待控制台出现 "继续..." 字样, 再进行下一次点击.')
                        print(f'请在点击后等待 {wait_seconds_after_touch} s , 待控制台出现 "继续..." 字样, 再进行下一次点击.')
                        print(f'请在点击后等待 {wait_seconds_after_touch} s , 待控制台出现 "继续..." 字样, 再进行下一次点击.')
                        print(f'准备开始录制 {record_name}...')
                        helper.create_custom_record(record_name, roi_size=64,
                                                        description=f"从主线一路点击进入{stage_category}关卡",
                                                        wait_seconds_after_touch=wait_seconds_after_touch)
                    # 录完了 刷一波
                    if stage['stage'].find('-') != -1:
                        _, stage_map_linear = get_stage(stage['stage'])
                        while True:
                            try:
                                helper.find_and_tap_stage_by_ocr(partition=None, target=stage['stage'], partition_map=stage_map_linear)
                            except RuntimeError:
                                # 活动关识别失败，程序重新尝试识别
                                logger.info('关卡 [%s] 识别失败, 尝试重新识别' % stage['stage'])
                            else:
                                break
                        c_id, remain = helper.module_battle_slim(stage['stage'], 1)
                    else:
                        c_id, remain = helper.module_battle_slim(None, 1)
                else:
                    # 存在点击路径 进行点击
                    helper.replay_custom_record(record_name)
                    # 判断支线关卡/剿灭作战
                    if stage['stage'].find('-') != -1:
                        _, stage_map_linear = get_stage(stage['stage'])
                        while True:
                            try:
                                helper.find_and_tap_stage_by_ocr(partition=None, target=stage['stage'], partition_map=stage_map_linear)
                            except RuntimeError:
                                # 活动关识别失败，程序重新尝试识别
                                logger.info('关卡 [%s] 识别失败, 尝试重新识别' % stage['stage'])
                            else:
                                break
                        c_id, remain = helper.module_battle_slim(stage['stage'], 1)
                    else:
                        c_id, remain = helper.module_battle_slim(None, 1)

            if remain == 1: # 理智不足未进行单次任务执行
                has_remain_sanity = False
                # 退出遍历
                break
            else: # 成功执行一次任务
                stage['remain'] = stage.get('remain', stage['count']) - 1
                with open('user_file/plan.json', 'w', encoding='utf-8') as f:
                    json.dump(plan, f, indent=4, sort_keys=False, ensure_ascii = False)
                break # 重新进行优先级遍历

    helper.back_to_main()
    logger.info('理智已清空')


def run_friend():

    helper, _ = _create_helper()

    logger.warning('开始访问好友')
    helper.get_credit()
    helper.mouse_click([(24,17),(150,55)])
    helper.wait(2)
    helper.mouse_click([(650,480),(1265,536)])
    helper.wait(5)
    helper.back_to_main()

def run_ship():

    helper, _ = _create_helper()

    logger.warning('开始收基建')
    helper.mouse_click([(950,590),(1120,670)])
    helper.wait(10)
    helper.mouse_click([(1180,76),(1274,110)])
    helper.wait(2)
    helper.mouse_click([(169,680),(303,707)])
    helper.wait(2)
    helper.mouse_click([(169,680),(303,707)])
    helper.wait(2)
    helper.mouse_click([(169,680),(303,707)])
    helper.wait(2)
    helper.mouse_click([(169,680),(303,707)])
    helper.wait(2)
    helper.mouse_click([(169,680),(303,707)])
    helper.wait(2)
    helper.mouse_click([(24,17),(150,55)])
    helper.wait(2)
    helper.mouse_click([(650,480),(1265,536)])
    helper.wait(5)
    helper.back_to_main()

def run_task():

    helper, _ = _create_helper()

    logger.warning('开始收任务奖励')
    helper.clear_task()
    helper.back_to_main()

def print_plan():

    with open('user_file/plan.json', 'r', encoding='utf-8') as f:
        plan = json.load(f)
    
    print_plan_with_plan(plan)
    print_sanity_usage(plan)

def get_good_stage_id(stages_same_prior):
    stage_ok_id = -1
    max_remain_ratio = 0
    for i in range(len(stages_same_prior)):
        stage = stages_same_prior[i]
        remain_ratio = stage.get('remain', stage['count']) / stage['count']
        if stage['stage'] not in list_not_open and stage.get('remain', stage['count']) > 0 and remain_ratio > max_remain_ratio:
            stage_ok_id = i
            max_remain_ratio = remain_ratio
    return stage_ok_id


def print_plan_with_plan(plan):
    logger.warning("当前刷图计划：")
    logger.info("---------------------------------------------------------------------------------------")
    logger.info("优先  " + "关卡".ljust(12) + "理智".ljust(5) + "计划".ljust(5) + "剩余".ljust(5) + "余比".ljust(8) + "备注")
    logger.info("---------------------------------------------------------------------------------------")
    prior = 1
    ok_task_used = False
    for tasks_same_prior in plan['stages']:
        stages_same_prior = tasks_same_prior['stages']
        ok_id = get_good_stage_id(stages_same_prior)
        for task_id, task in enumerate(stages_same_prior):
            remain = task.get('remain', task['count'])
            fini_percent = int((remain / task['count']) * 100)
            if fini_percent == 0:
                status_char = '√'
            elif task['stage'] in list_not_open:
                status_char = '×'
            elif task_id == ok_id and ok_task_used == False:
                status_char = '○'
                ok_task_used = True
            else:
                status_char = ' '
            if fini_percent == 100 or task['count'] == 9999 or fini_percent == 0:
                logger.info(str(prior).ljust(6) + task['stage'].ljust(14-int((len(task['stage'].encode('utf-8'))-len(task['stage']))/2)) + str(task.get('sanity', '')).ljust(7) + str(task['count']).ljust(7) + str(remain).ljust(7) + " --  " + status_char + "    " + task['//'])
            else:
                logger.info(str(prior).ljust(6) + task['stage'].ljust(14-int((len(task['stage'].encode('utf-8'))-len(task['stage']))/2)) + str(task.get('sanity', '')).ljust(7) + str(task['count']).ljust(7) + str(remain).ljust(7) + str(fini_percent).rjust(3) + "% " + status_char + "    " + task['//'])
        logger.info("---------------------------------------------------------------------------------------")
        prior += 1

def print_sanity_usage(plan):
    prior = 1
    now_prior = -1
    ok_task_used = False
    for tasks_same_prior in plan['stages']:
        stages_same_prior = tasks_same_prior['stages']
        ok_id = get_good_stage_id(stages_same_prior)
        for task_id, task in enumerate(stages_same_prior):
            remain = task.get('remain', task['count'])
            fini_percent = int((remain / task['count']) * 100)
            if fini_percent == 0:
                status_char = '√'
            elif task['stage'] in list_not_open:
                status_char = '×'
            elif task_id == ok_id and ok_task_used == False:
                status_char = '○'
                now_prior = prior
                ok_task_used = True
            else:
                status_char = ' '
        prior += 1
        if ok_task_used:
            break
    if now_prior != -1:
        sanity_usage = 0
        for task in plan['stages'][now_prior-1]['stages']:
            sanity_usage += task.get('remain', task['count']) * task.get('sanity', 0)
        hour_rest = sanity_usage / 240 * 24
        hour_rest_monthly = sanity_usage // 300 * 24 + sanity_usage % 300 / 10
        if hour_rest >= 24:
            str_hour_rest = str(int(hour_rest//24)) + " 天 " + str(int(hour_rest%24)+1) + " 小时"
        else:
            str_hour_rest = str(int(hour_rest%24)+1) + " 小时"
        if hour_rest_monthly >= 24:
            str_hour_rest_monthly = str(int(hour_rest_monthly//24)) + " 天 " + str(int(hour_rest_monthly%24)+1) + " 小时"
        else:
            str_hour_rest_monthly = str(int(hour_rest_monthly%24)+1) + " 小时"
        logger.info("仍需：" + str(sanity_usage) + " 理智  -  " + str_hour_rest + " / " + str_hour_rest_monthly + " (Prime)")



def run_print_plan():

    print("\n\n\n\n\n\n\n\n\n\n\n\n")

    print_plan()


def clear_task_not_open():
    global list_not_open
    list_not_open = []
    

if __name__ == '__main__':

    assert os.path.exists('user_file/plan.json'), '未能检测到刷图计划文件.'

    run_print_plan()
    run_plan()
    
    schedule.clear()

    schedule.every(1).hours.at(":10").do(run_ship)
    schedule.every(1).hours.at(":30").do(run_task)
    schedule.every(1).hours.at(":50").do(run_friend)

    schedule.every(1).day.at("04:15").do(clear_task_not_open)

    schedule.every(1).day.at("00:00").do(run_plan)
    schedule.every(1).day.at("01:00").do(run_plan)
    schedule.every(1).day.at("02:00").do(run_plan)
    schedule.every(1).day.at("03:00").do(run_plan)

    schedule.every(1).day.at("05:00").do(run_plan)
    schedule.every(1).day.at("06:00").do(run_plan)
    schedule.every(1).day.at("07:00").do(run_plan)
    schedule.every(1).day.at("08:00").do(run_plan)
    schedule.every(1).day.at("09:00").do(run_plan)
    schedule.every(1).day.at("10:00").do(run_plan)
    schedule.every(1).day.at("11:00").do(run_plan)
    schedule.every(1).day.at("12:00").do(run_plan)
    schedule.every(1).day.at("13:00").do(run_plan)
    schedule.every(1).day.at("14:00").do(run_plan)
    schedule.every(1).day.at("15:00").do(run_plan)
    schedule.every(1).day.at("16:00").do(run_plan)
    schedule.every(1).day.at("17:00").do(run_plan)
    schedule.every(1).day.at("18:00").do(run_plan)
    schedule.every(1).day.at("19:00").do(run_plan)
    schedule.every(1).day.at("20:00").do(run_plan)
    schedule.every(1).day.at("21:00").do(run_plan)
    schedule.every(1).day.at("22:00").do(run_plan)
    schedule.every(1).day.at("23:00").do(run_plan)

    schedule.every(1).day.at("00:20").do(run_plan)
    schedule.every(1).day.at("01:20").do(run_plan)
    schedule.every(1).day.at("02:20").do(run_plan)
    schedule.every(1).day.at("03:20").do(run_plan)
    schedule.every(1).day.at("04:20").do(run_plan)
    schedule.every(1).day.at("05:20").do(run_plan)
    schedule.every(1).day.at("06:20").do(run_plan)
    schedule.every(1).day.at("07:20").do(run_plan)
    schedule.every(1).day.at("08:20").do(run_plan)
    schedule.every(1).day.at("09:20").do(run_plan)
    schedule.every(1).day.at("10:20").do(run_plan)
    schedule.every(1).day.at("11:20").do(run_plan)
    schedule.every(1).day.at("12:20").do(run_plan)
    schedule.every(1).day.at("13:20").do(run_plan)
    schedule.every(1).day.at("14:20").do(run_plan)
    schedule.every(1).day.at("15:20").do(run_plan)
    schedule.every(1).day.at("16:20").do(run_plan)
    schedule.every(1).day.at("17:20").do(run_plan)
    schedule.every(1).day.at("18:20").do(run_plan)
    schedule.every(1).day.at("19:20").do(run_plan)
    schedule.every(1).day.at("20:20").do(run_plan)
    schedule.every(1).day.at("21:20").do(run_plan)
    schedule.every(1).day.at("22:20").do(run_plan)
    schedule.every(1).day.at("23:20").do(run_plan)

    schedule.every(1).day.at("00:40").do(run_plan)
    schedule.every(1).day.at("01:40").do(run_plan)
    schedule.every(1).day.at("02:40").do(run_plan)
    
    schedule.every(1).day.at("04:40").do(run_plan)
    schedule.every(1).day.at("05:40").do(run_plan)
    schedule.every(1).day.at("06:40").do(run_plan)
    schedule.every(1).day.at("07:40").do(run_plan)
    schedule.every(1).day.at("08:40").do(run_plan)
    schedule.every(1).day.at("09:40").do(run_plan)
    schedule.every(1).day.at("10:40").do(run_plan)
    schedule.every(1).day.at("11:40").do(run_plan)
    schedule.every(1).day.at("12:40").do(run_plan)
    schedule.every(1).day.at("13:40").do(run_plan)
    schedule.every(1).day.at("14:40").do(run_plan)
    schedule.every(1).day.at("15:40").do(run_plan)
    schedule.every(1).day.at("16:40").do(run_plan)
    schedule.every(1).day.at("17:40").do(run_plan)
    schedule.every(1).day.at("18:40").do(run_plan)
    schedule.every(1).day.at("19:40").do(run_plan)
    schedule.every(1).day.at("20:40").do(run_plan)
    schedule.every(1).day.at("21:40").do(run_plan)
    schedule.every(1).day.at("22:40").do(run_plan)
    schedule.every(1).day.at("23:40").do(run_plan)


    while True:
        schedule.run_pending()
        if schedule.idle_seconds()>0:
            run_print_plan()
            timenow = datetime.datetime.now()
            nexttask_str = {
                5: '刷图',
                0: '收基建',
                1: '刷图',
                2: '收任务',
                3: '刷图',
                4: '访问好友'
            }[(timenow.minute // 10)]
            timenext = (datetime.datetime.now() + datetime.timedelta(seconds=schedule.idle_seconds())).time()
            logger.info('计划：将于 ' + timenext.isoformat(timespec='minutes') + ' 开始 ' + nexttask_str)
            time.sleep(schedule.idle_seconds())
