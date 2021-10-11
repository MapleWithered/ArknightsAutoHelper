import copy
import datetime
import json
import logging
import math
import os
import time

import requests
from ruamel import yaml

import schedule

import imgreco
from Arknights.helper import logger
from Arknights.shell_next import _create_helper
import Arknights.stage_path
from addons.activity import get_stage
from Arknights.flags import *
from imgreco import before_operation
from penguin_stats import arkplanner

from vendor.ArkPlanner.MaterialPlanning import MaterialPlanning

mp = MaterialPlanning(update=True)

# arkplanner离线后备
# 刷钱
# GUI

stages_not_open = []

path_plan = '007/plan.yaml'
path_aog = '007/cache/aog.yaml'
path_config = '007/config/'

helper, _ = _create_helper()


def load_plan_json():
    assert os.path.exists(path_plan), '未能检测到刷图计划文件.'
    with open(path_plan, 'r', encoding='utf-8') as f:
        plan = json.load(f)
    return plan


def dump_plan_json(plan):
    with open(path_plan, 'w', encoding='utf-8') as f:
        json.dump(plan, f, indent=4, sort_keys=False, ensure_ascii=False)


def item_id_to_name(id):
    all_items = arkplanner.get_all_items()
    for item in all_items:
        if item['itemId'] == id:  # and item['rarity'] == 2
            return item['name']


def item_name_to_id(name):
    all_items = arkplanner.get_all_items()
    for item in all_items:
        if item['name'] == name:  # and item['rarity'] == 2
            return item['itemId']


def load_plan_yaml():
    assert os.path.exists(path_plan), '未能检测到刷图计划文件.'
    with open(path_plan, 'r', encoding='utf-8') as f:
        plan = yaml.load(f.read(), Loader=yaml.RoundTripLoader)
    # 填充理智数据
    need_dump = False
    for priority in plan['plan']:
        if list(priority)[0] == 'stages':
            stages_same_prior = priority['stages']
            for i in range(len(stages_same_prior)):
                stage_data = stages_same_prior[i]
                if 'sanity' not in list(stage_data):
                    need_dump = True
                    stage_data['sanity'] = get_stage_sanity(list(stage_data)[0])
                if 'remain' not in list(stage_data):
                    need_dump = True
                    stage_data['remain'] = stage_data[list(stage_data)[0]]
    if need_dump:
        dump_plan_yaml(plan)
    return plan


def dump_plan_yaml(plan):
    with open(path_plan, 'w', encoding='utf-8') as f:
        yaml.dump(plan, f, Dumper=yaml.RoundTripDumper, indent=2, allow_unicode=True, encoding='utf-8')


def load_config():
    config = {}
    with open(path_config + 'item_excluded.yaml', 'r', encoding='utf-8') as f:
        config['item_excluded'] = yaml.load(f.read(), Loader=yaml.RoundTripLoader)
    with open(path_config + 'stage_unavailable.yaml', 'r', encoding='utf-8') as f:
        config['stage_unavailable'] = yaml.load(f.read(), Loader=yaml.RoundTripLoader)
    with open(path_config + 'config.yaml', 'r', encoding='utf-8') as f:
        config.update(yaml.load(f.read(), Loader=yaml.RoundTripLoader))
    return config


def load_aog_data():
    if not os.path.exists(path_aog):
        logger.info('未检测到一图流关卡数据，正在拉取')
        aog_data = requests.get('https://arkonegraph.herokuapp.com/total/CN').json()
        with open(path_aog, 'w', encoding='utf-8') as f:
            yaml.dump(aog_data, f, Dumper=yaml.RoundTripDumper, indent=4, allow_unicode=True, encoding='utf-8')
        logger.info('拉取完成，存放在{path_aog}')
    else:
        with open(path_aog, 'r', encoding='utf-8') as f:
            aog_data = yaml.load(f.read(), Loader=yaml.RoundTripLoader)
    return aog_data


def load_inventory():
    my_inventory = helper.get_inventory_items(True)
    for item in my_inventory:
        if my_inventory[item] is None:
            my_inventory[item] = 0
    return my_inventory


def aog_order_stage(item_data):
    list_stages = []
    for stage in item_data['lowest_ap_stages']['normal']:
        if [stage['code'], stage['efficiency']] not in list_stages:
            list_stages.append([stage['code'], stage['efficiency']])
    for stage in item_data['lowest_ap_stages']['event']:
        if [stage['code'], stage['efficiency']] not in list_stages:
            list_stages.append([stage['code'], stage['efficiency']])
    for stage in item_data['balanced_stages']['normal']:
        if [stage['code'], stage['efficiency']] not in list_stages:
            list_stages.append([stage['code'], stage['efficiency']])
    for stage in item_data['balanced_stages']['event']:
        if [stage['code'], stage['efficiency']] not in list_stages:
            list_stages.append([stage['code'], stage['efficiency']])
    for stage in item_data['drop_rate_first_stages']['normal']:
        if [stage['code'], stage['efficiency']] not in list_stages:
            list_stages.append([stage['code'], stage['efficiency']])
    for stage in item_data['drop_rate_first_stages']['event']:
        if [stage['code'], stage['efficiency']] not in list_stages:
            list_stages.append([stage['code'], stage['efficiency']])
    list_stages.sort(reverse=True, key=(lambda x: x[1]))
    return list_stages


def get_my_item_count(item_name, my_items=None):
    if my_items is None:
        my_items = load_inventory()
    # logger.info("从在线数据库中获取游戏物品列表")
    if item_name_to_id(item_name) in list(my_items):
        return my_items[item_name_to_id(item_name)]
    else:
        return 0


def print_all_items_name():
    all_items = arkplanner.get_all_items()
    for item in all_items:
        if item['itemType'] in ['MATERIAL']:  # and item['rarity'] == 2
            print(item['name'])


def get_min_blue_item_stage(item_excluded=None, stage_unavailable=None, my_items=None):
    config = load_config()
    if item_excluded is None:
        item_excluded = config['item_excluded']
    if stage_unavailable is None:
        stage_unavailable = config['stage_unavailable']
    aog_data = load_aog_data()
    if my_items is None:
        my_items = load_inventory()
    all_items = arkplanner.get_all_items()
    list_my_blue_item = []
    for item in all_items:
        if item['itemType'] in ['MATERIAL'] and item['name'] not in item_excluded and item['rarity'] == 2 \
                and len(item['itemId']) > 4:
            list_my_blue_item.append({'name': item['name'],
                                      'itemId': item['itemId'],
                                      'count': my_items.get(item['itemId'], 0),
                                      'rarity': item['rarity']})
    list_my_blue_item = sorted(list_my_blue_item, key=lambda x: x['count'])
    # print('require item: %s, owned: %s, need ' % (list_my_blue_item[0]['name'], list_my_blue_item[0]['count']))
    second_count = list_my_blue_item[0]['count']
    for i in range(len(list_my_blue_item)):
        if list_my_blue_item[i]['count'] > list_my_blue_item[0]['count']:
            second_count = list_my_blue_item[i]['count']
            break
    else:
        second_count += 9999
    # return [list_my_blue_item[0]['name'], list_my_blue_item[0]['count'], (second_count-list_my_blue_item[0]['count'])]
    # 获得了要刷的最少蓝材料 以及蓝材料的个数

    blue_items_data = aog_data['tier']['t3']
    stage_todo = None
    i = 0
    while i < len(list_my_blue_item):  # 要刷的蓝材料从自己最少的蓝材料开始
        item_seen = False
        for aog_blue_item in blue_items_data:
            if aog_blue_item['name'] == list_my_blue_item[i]['name']:  # 对于需要刷的这个蓝材料
                item_seen = True
                stage_info = aog_order_stage(aog_blue_item)
                for stage in stage_info:  # 对于能刷的关卡表
                    if stage[0] not in stage_unavailable:  # 如果这个关卡能刷
                        stage_todo = stage[0]
                        logger.info('蓝材料:' + list_my_blue_item[i]['name'] + ',  关卡:' + stage_todo)
                        return stage_todo
        i += 1
    return None


def goto_stage_special_record(stage_name, config=None):
    if config is None:
        config = load_config()
    helper.back_to_main()
    # 得到关卡前缀
    if stage_name.rfind('-') == -1:
        stage_category = stage_name
    else:
        stage_category = stage_name[:stage_name.rfind('-')]
    record_name = f"main_to_{stage_category}"
    # 判断点击路径是否存在
    if not os.path.exists(f'custom_record/{record_name}/record.json'):
        # 不存在点击路径 进行录制
        logger.warning(f"当前关卡{stage_category}，未录制点击路径。")
        c = input(f'是否录制相应操作记录(需要 MuMu 模拟器)[y/N]:').strip().lower()
        if c != 'y':
            # 用户不希望录制 当日内忽略此关卡
            stages_not_open.append(stage_name)
            logger.info(f"今日将忽略 {stage_name} 关卡")
            return -1
        # 希望录制 判断支线关卡/剿灭作战
        if stage_name.find('-') != -1:
            # 支线活动关卡
            wait_seconds_after_touch = 4
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
            wait_seconds_after_touch = 4
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
        if stage_name.find('-') != -1:
            _, stage_map_linear = get_stage(stage_name)
            try:
                helper.find_and_tap_stage_by_ocr(partition=None, target=stage_name,
                                                 partition_map=stage_map_linear)
                helper.wait(TINY_WAIT, MANLIKE_FLAG=False)
            except RuntimeError:
                # 活动关识别失败
                return -1
    else:
        # 存在点击路径 进行点击
        clickmode = 'point' if config.get("1280x720", False) else 'match_template'
        helper.replay_custom_record(record_name, mode=clickmode)
        # 判断支线关卡/剿灭作战
        if stage_name.find('-') != -1:
            try:
                _, stage_map_linear = get_stage(stage_name)
            except RuntimeError:
                return -1
            try:
                helper.find_and_tap_stage_by_ocr(partition=None, target=stage_name,
                                                 partition_map=stage_map_linear)
                helper.wait(TINY_WAIT, MANLIKE_FLAG=False)
            except RuntimeError:
                # 活动关名字识别失败
                return -1
    return 0


def goto_stage(stage):
    if stage == 'MN-8':
        stage = 'MN8'
    failure_count = 0
    while failure_count <= 2:
        if Arknights.stage_path.is_stage_supported_ocr(stage):
            try:
                helper.goto_stage_by_ocr(stage)
            except RuntimeError as err:
                if str(err) == "recognition failed":
                    failure_count += 1
                    continue
                else:
                    raise
            helper.wait(TINY_WAIT, MANLIKE_FLAG=False)
            if '-' in str(stage):
                if ensure_stage(stage) == 0:
                    return 0
            else:
                return 0
        elif '-' in str(stage):
            goto_stage_special_record(stage)
            if ensure_stage(stage) == 0:
                return 0
        else:
            goto_stage_special_record(stage)
            return 0
        failure_count += 1
    else:
        raise RuntimeError("Unable to goto stage.")


def ensure_stage(stage):
    helper.wait(1, MANLIKE_FLAG=False)
    count_times = 0
    while True:
        screenshot = helper.adb.screenshot()
        recoresult = imgreco.before_operation.recognize(screenshot)
        if recoresult is not None:
            logger.debug('当前画面关卡：%s', recoresult['operation'])
            if stage is not None:
                # 如果传入了关卡 ID，检查识别结果
                if recoresult['operation'] != stage:
                    # print(recoresult['operation'])
                    logger.error('不在关卡界面')
                    return -1
                else:
                    return 0
            break
        else:
            count_times += 1
            helper.wait(1, False)
            if count_times >= 7:
                logger.warning('不在关卡界面')
                helper.wait(TINY_WAIT, False)
                continue
            else:
                logger.error('{}次检测后都不再关卡界面'.format(count_times))
                return -1
    return 0


def get_stage_sanity(stage_id):
    all_stages = arkplanner.get_all_stages()
    for stage in all_stages:
        if stage.get('code', '') == stage_id:
            return stage.get('apCost', -1)


def run_plan():
    global stages_not_open
    config = load_config()

    plan = load_plan_yaml()
    assert plan['plan'], "刷图计划文件中未能检测到刷图计划，或格式错误"

    update_refill_config(plan)

    logger.warning('开始刷图')

    has_remain_sanity = True

    my_inventory = {}
    inventory_loaded = False

    while has_remain_sanity:
        priority_id = 0
        for priority in plan['plan']:
            if list(priority)[0] != 'stages' and inventory_loaded is False:
                my_inventory: dict = load_inventory()
                inventory_loaded = True
                break
        for priority in plan['plan']:
            priority_id += 1
            print_plan_with_plan(plan, my_inventory=my_inventory, print_priority=priority_id)
            if list(priority)[0] == 'stages':
                stages_same_prior = priority['stages']
                # 找出符合要求的关卡：余比最高的开放关卡
                stage_ok_id = get_good_stage_id(stages_same_prior)
                if stage_ok_id == -1:
                    logger.warning('优先级 ' + str(priority_id) + ' 无剩余未完成开放关卡')
                    continue  # 没有未完成的开放关卡，下一优先级
                stage_data = stages_same_prior[stage_ok_id]
                stage_name = list(stage_data)[0]
                stage_count = stage_data[list(stage_data)[0]]
                stage_remain = stage_data['remain']
                logger.warning('优先级: %s, 关卡 [%s], 总计划: %s, 剩余次数: %s, 备注: %s' % (
                    priority_id, stage_name, stage_count, stage_remain, stage_data['//']))
                try:
                    # 执行未完成的开放关卡一次
                    goto_stage(stage_name)
                    _, remain = helper.module_battle_slim(set_count=1)
                    inventory_loaded = False
                    if remain == 1:  # 理智不足未进行单次任务执行
                        has_remain_sanity = False
                        # 退出遍历
                        break
                    else:  # 成功执行一次任务
                        stage_data['remain'] -= 1
                        dump_plan_yaml(plan)
                        break  # 重新进行优先级遍历

                except RuntimeError:
                    # 未开放，加入未开放关卡列表中
                    logger.info('关卡 [%s] 未开放, 继续下一关卡' % stage_name)
                    stages_not_open.append(stage_name)
                    logger.info('当日未开放关卡列表：' + str(stages_not_open))
                    break  # 重新进行优先级遍历
            elif list(priority)[0] == 'blue_item':
                logger.warning("优先级: " + str(priority_id) + ", 刷仓库中最少的蓝材料")
                min_blue_stage = get_min_blue_item_stage(my_items=my_inventory)
                logger.warning('优先级: %s, 关卡 [%s]' % (
                    priority_id, min_blue_stage))
                goto_stage(min_blue_stage)
                _, remain = helper.module_battle_slim(min_blue_stage, 1)
                inventory_loaded = False
                if remain == 1:  # 理智不足未进行单次任务执行
                    has_remain_sanity = False
                    # 退出遍历
                break
            elif list(priority)[0] == 'planner':
                item_list = []
                for item in priority[list(priority)[0]]:
                    item_num_had = get_my_item_count(list(item)[0], my_inventory)
                    item_num_need = item[list(item)[0]]
                    item_name = list(item)[0]
                    if item_num_need > 0:
                        item_list.append([item_name, item_num_need])
                arkplanner_result = create_plan_by_item(item_list, my_inventory)
                if len(arkplanner_result[0]) > 0:
                    logger.warning('优先级: %s, 关卡 [%s], 剩余次数: %s' % (
                        priority_id, arkplanner_result[0][0]['stage'], arkplanner_result[0][0]['count']))
                    goto_stage(arkplanner_result[0][0]['stage'])
                    _, remain = helper.module_battle_slim(arkplanner_result[0][0]['stage'], 1)
                    inventory_loaded = False
                    if remain == 1:  # 理智不足未进行单次任务执行
                        has_remain_sanity = False
                        # 退出遍历
                    break
                else:
                    logger.warning('优先级 ' + str(priority_id) + ' 无剩余未完成开放关卡')
                    continue  # 没有未完成的开放关卡，下一优先级
    helper.back_to_main()
    logger.info('理智已清空')


def update_refill_config(plan):
    if 'refill_with_item' in list(plan):
        helper.refill_with_item = plan['refill_with_item']
        helper.use_refill = helper.refill_with_item
    else:
        helper.refill_with_item = False
        helper.use_refill = False
    helper.refill_with_originium = False


def run_friend():
    logger.warning('开始访问好友')
    helper.get_credit()
    helper.back_to_main()


def run_ship():
    logger.warning('开始收基建')
    helper.get_building()
    helper.back_to_main()


def run_task():
    logger.warning('开始收任务奖励')
    helper.clear_task()
    helper.back_to_main()


def print_plan(my_inventory=None):
    if my_inventory is None:
        my_inventory = load_inventory()
    plan = load_plan_yaml()

    print_plan_with_plan(plan, my_inventory=my_inventory)


def get_good_stage_id(stages_same_prior):
    config = load_config()
    stage_ok_id = -1
    max_remain_ratio = 0
    for i in range(len(stages_same_prior)):
        stage_data = stages_same_prior[i]
        stage_name = list(stage_data)[0]
        stage_count = stage_data[list(stage_data)[0]]
        if 'remain' not in list(stage_data):
            stage_data['remain'] = copy.deepcopy(stage_count)
        remain_ratio = stage_data['remain'] / stage_count
        if stage_name not in stages_not_open + config['stage_unavailable'] and stage_data['remain'] > 0 \
                and remain_ratio > max_remain_ratio:
            stage_ok_id = i
            max_remain_ratio = remain_ratio
    return stage_ok_id


def create_plan_by_item(item_list, my_inventory=None):
    required = {}
    owned = {}

    for item_need in item_list:
        required[item_need[0]] = item_need[1]

    if my_inventory is None:
        my_inventory = load_inventory()

    for item_had in my_inventory:
        owned[item_id_to_name(item_had)] = my_inventory[item_had]

    config = load_config()
    excluded = config['stage_unavailable']

    # c = input('是否获取当前库存材料数量(y,N):')
    # if c.lower() == 'y':
    #     from Arknights.shell_next import _create_helper
    #     owned = _create_helper()[0].get_inventory_items()
    # calc_mode = config.get('plan/calc_mode', 'online')
    plan = mp.get_plan(required, owned, print_output=False, outcome=True, convertion_dr=0.17,
                       input_lang='zh', output_lang='zh', exclude=excluded)

    # print('正在获取刷图计划...')
    # if calc_mode == 'online':
    #     plan = arkplanner.get_plan(required, owned)
    # elif calc_mode == 'local-aog':
    #     from penguin_stats.MaterialPlanning import MaterialPlanning
    #     mp = MaterialPlanning()
    #     plan = mp.get_plan(requirement_dct=required, deposited_dct=owned)
    # else:
    #     raise RuntimeError(f'不支持的模式: {calc_mode}')
    stage_task_list = []
    # print(plan)
    # print('刷图计划:')
    for stage in plan['stages']:
        stage_name = stage['stage']
        count = math.ceil(float(stage['count']))
        # print('关卡 [%s] 次数 %s' % (stage_name, count))
        stage_task_list.append({'stage': stage_name, 'count': count, 'cost': get_stage_sanity(stage_name)})
    # print(stage_task_list)
    return stage_task_list, plan['cost']


def print_plan_with_plan(plan, my_inventory, print_priority=None):
    if print_priority is None:
        logger.info("\n\n\n\n\n\n\n\n\n\n\n\n")
        logger.warning("当前刷图计划：")

    logger.info("----------------------------------------------------------------------------------------")

    prior = 1
    ok_task_used = False
    ok_cost = None

    for priority in plan['plan']:
        priority_first_line = True
        if list(priority)[0] == 'stages':
            if print_priority == prior or print_priority is None:
                logger.info(
                    "优先  " + "关卡".ljust(12) + "理智".ljust(5) + "计划".ljust(5) + "剩余".ljust(5) + "余比".ljust(8) + "备注")
            stages_same_prior = priority['stages']
            ok_id = get_good_stage_id(stages_same_prior)
            for task_id, task in enumerate(stages_same_prior):
                remain = task['remain']
                fini_percent = int((remain / task[list(task)[0]]) * 100)
                if fini_percent == 0:
                    status_char = '√'
                elif list(task)[0] in stages_not_open:
                    status_char = '×'
                elif task_id == ok_id and ok_task_used is False:
                    status_char = '○'
                    ok_task_used = prior - 1
                else:
                    status_char = ' '
                if priority_first_line:
                    priority_first_line = False
                    priority_str = ' ' + str(prior).zfill(2).ljust(5)
                else:
                    priority_str = '      '
                if print_priority == prior or print_priority is None:
                    if fini_percent == 100 or task[list(task)[0]] >= 1000 or fini_percent == 0:
                        logger.info(priority_str + list(task)[0].ljust(
                            14 - int((len(list(task)[0].encode('utf-8')) - len(list(task)[0])) / 2)) + str(
                            task.get('sanity', '')).ljust(7) + str(task[list(task)[0]]).ljust(7) + str(remain).ljust(
                            7) + " --  " + status_char + "    " + task['//'])
                    else:
                        logger.info(priority_str + list(task)[0].ljust(
                            14 - int((len(list(task)[0].encode('utf-8')) - len(list(task)[0])) / 2)) + str(
                            task.get('sanity', '')).ljust(7) + str(task[list(task)[0]]).ljust(7) + str(remain).ljust(
                            7) + str(
                            fini_percent).rjust(3) + "% " + status_char + "    " + task['//'])
            if print_priority == prior or print_priority is None:
                logger.info("----------------------------------------------------------------------------------------")
        elif list(priority)[0] == 'blue_item':
            if print_priority == prior or print_priority is None:
                logger.info("优先  " + "任务".ljust(12))
            if ok_task_used is False:
                status_char = '○'
                ok_task_used = prior - 1
            else:
                status_char = ' '
            if print_priority == prior or print_priority is None:
                logger.info(' ' + str(prior).zfill(2).ljust(5) + '@BLUE_ITEM'.ljust(20) + status_char)
                logger.info("----------------------------------------------------------------------------------------")
        elif list(priority)[0] == 'planner':
            if print_priority == prior or print_priority is None:
                logger.info("优先  " + "物品".ljust(12) + "已有".ljust(5) + "计划".ljust(5) + "仍需".ljust(5))
            item_list = []
            for item in priority[list(priority)[0]]:
                item_num_had = get_my_item_count(list(item)[0], my_inventory)
                item_num_need = item[list(item)[0]]
                item_name = list(item)[0]
                if item_num_need > 0:
                    item_list.append([item_name, item_num_need])
                # print('utf8', len(item_name.encode('utf-8')), len(item_name))
                if priority_first_line:
                    priority_first_line = False
                    priority_str = ' ' + str(prior).zfill(2).ljust(5)
                else:
                    priority_str = '      '
                if print_priority == prior or print_priority is None:
                    logger.info(
                        priority_str + item_name.ljust(
                            14 - int((len(item_name.encode('utf-8')) - len(item_name)) / 2)) +
                        str(item_num_had).ljust(7) + str(item[list(item)[0]]).ljust(7) +
                        str(max(item_num_need - item_num_had, 0)).ljust(8))
            arkplanner_result = create_plan_by_item(item_list, my_inventory)
            if len(arkplanner_result[0]) > 0:
                # logger.info("      ↓             ↓      ↓      ↓             -  -  -  -     arkplanner     -  -  -  -")
                if print_priority == prior or print_priority is None:
                    logger.info(
                        "                                                   -  -  ↓     arkplanner     ↓  -  -   ")
                    logger.info("      " + "关卡".ljust(12) + "理智".ljust(5) + "计划".ljust(5))
                for stage in arkplanner_result[0]:
                    if ok_task_used is False:
                        ok_task_used = prior - 1
                        ok_cost = arkplanner_result[1]
                        status_char = '○'
                    else:
                        status_char = ' '
                    if print_priority == prior or print_priority is None:
                        logger.info(''.ljust(6) + stage['stage'].ljust(
                            14 - int((len(stage['stage'].encode('utf-8')) - len(stage['stage'])) / 2)) + str(
                            stage['cost']).ljust(7) + str(stage['count']).ljust(7) + ''.ljust(7) + ''.rjust(
                            3) + "  " + status_char)
                # logger.info(str(prior).ljust(6) + '@BLUE_ITEM')
            if print_priority == prior or print_priority is None:
                logger.info("----------------------------------------------------------------------------------------")
        prior += 1

    ok_priority_data = plan['plan'][ok_task_used][list(plan['plan'][ok_task_used])[0]]
    ok_priority_category = list(plan['plan'][ok_task_used])[0]
    if ok_priority_category == 'stages':
        ok_cost = 0
        for stage in ok_priority_data:
            ok_cost += stage['sanity'] * stage['remain']

    if ok_cost is not None and (ok_task_used + 1 == print_priority or print_priority is None):
        print_sanity_usage(ok_cost)


def print_sanity_usage(sanity):
    hour_rest = sanity / 240 * 24
    hour_rest_monthly = sanity // 300 * 24 + sanity % 300 / 10
    if hour_rest >= 24:
        str_hour_rest = str(int(hour_rest // 24)) + " 天 " + str(int(hour_rest % 24) + 1) + " 小时"
    else:
        str_hour_rest = str(int(hour_rest % 24) + 1) + " 小时"
    if hour_rest_monthly >= 24:
        str_hour_rest_monthly = str(int(hour_rest_monthly // 24)) + " 天 " + str(
            int(hour_rest_monthly % 24) + 1) + " 小时"
    else:
        str_hour_rest_monthly = str(int(hour_rest_monthly % 24) + 1) + " 小时"
    logger.info("仍需：" + str(sanity) + " 理智  -  " + str_hour_rest + " / " + str_hour_rest_monthly + " (Prime)")


def run_print_plan(my_inventory=None):
    if my_inventory is None:
        my_inventory = load_inventory()
    print_plan(my_inventory=my_inventory)


def clear_task_not_open():
    global stages_not_open
    stages_not_open = []


def run_update_data():
    arkplanner.update_cache()


if __name__ == '__main__':

    assert os.path.exists(path_plan), '未能检测到刷图计划文件.'

    init_inventory = load_inventory()

    run_print_plan(init_inventory)
    run_plan()
    run_update_data()

    run_ship()
    run_friend()
    run_task()

    schedule.clear()

    schedule.every(1).hours.at(":10").do(run_ship)
    schedule.every(1).hours.at(":30").do(run_task)
    schedule.every(1).hours.at(":50").do(run_friend)

    schedule.every(1).day.at("04:15").do(clear_task_not_open)
    schedule.every(1).day.at("04:00").do(run_update_data)

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
        if schedule.idle_seconds() > 0:
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
