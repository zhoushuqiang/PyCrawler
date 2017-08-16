# -*- coding:UTF-8  -*-
"""
88mm图库图片爬虫
http://www.88mmw.com/
@author: hikaru
email: hikaru870806@hotmail.com
如有问题或建议请联系
"""
from common import log, net, robot, tool
import os
import re
import threading
import time
import traceback

SUB_PATH_LIST = {
    "Rosi": 1,
    "Sibao": 2,
    "Tpimage": 3,
    "RiBen": 4,
    "Dgxz": 5,
    "Pansi": 6,
    "Sityle": 7,
    "JiePai": 8,
    "GaoQing": 9,
}
ACCOUNTS = []
TOTAL_IMAGE_COUNT = 0
IMAGE_DOWNLOAD_PATH = ""
NEW_SAVE_DATA_PATH = ""


# 获取指定一页的图集
def get_one_page_album(sub_path, page_count):
    album_pagination_url = "http://www.88mmw.com/%s/list_%s_%s.html" % (sub_path, SUB_PATH_LIST[sub_path], page_count)
    album_pagination_response = net.http_request(album_pagination_url)
    result = {
        "is_over": False,  # 是不是最后一页图集
        "album_info_list": [],  # 所有图集信息
    }
    if album_pagination_response.status != net.HTTP_RETURN_CODE_SUCCEED:
        raise robot.RobotException(robot.get_http_request_failed_reason(album_pagination_response.status))
    # 页面编码
    album_pagination_html = album_pagination_response.data.decode("GBK").encode("UTF-8")
    # 获取图集信息
    album_info_html = tool.find_sub_string(album_pagination_html, '<div class="xxx">', "</div>")
    if not album_info_html:
        album_info_html = tool.find_sub_string(album_pagination_html, '<div class="yyy">', "</div>")
    if not album_info_html:
        raise robot.RobotException("页面截取图集列表失败\n%s" % album_pagination_html)
    album_info_list = re.findall('<a href="/' + sub_path + '/(\d*)/" title="([^"]*)', album_info_html)
    if len(album_info_list) == 0:
        raise robot.RobotException("页面匹配图集信息失败\n%s" % album_info_html)
    for page_id, album_title in album_info_list:
        extra_album_info = {
            "page_id": str(page_id),  # 图集页面id
            "album_title": "",  # 图集id
        }
        # 获取图集标题
        if len(re.findall("_共\d*张", album_title)) == 1:
            extra_album_info["album_title"] = album_title[:album_title.rfind("_共")]
        else:
            extra_album_info["album_title"] = album_title
        result["album_info_list"].append(extra_album_info)
    # 判断是不是最后一页
    max_page_find = re.findall("<a href='list_1_(\d*).html'>末页</a>", album_pagination_html)
    if len(max_page_find) == 2 and max_page_find[0] == max_page_find[1] and robot.is_integer(max_page_find[0]):
        result['is_over'] = page_count >= int(max_page_find[0])
    else:
        result['is_over'] = True
    return result


# 获取图集一页的图片
def get_one_page_photo(sub_path, page_id, page_count):
    if page_count == 1:
        photo_pagination_url = "http://www.88mmw.com/%s/%s" % (sub_path, page_id)
    else:
        photo_pagination_url = "http://www.88mmw.com/%s/%s/index_%s.html" % (sub_path, page_id, page_count)
    photo_pagination_response = net.http_request(photo_pagination_url)
    result = {
        "is_over": False,  # 是不是图集的最后一页
        "image_url_list": [],  # 所有图片地址
    }
    if photo_pagination_response.status != net.HTTP_RETURN_CODE_SUCCEED:
        raise robot.RobotException(robot.get_http_request_failed_reason(photo_pagination_response.status))
    # 页面编码
    photo_pagination_html = photo_pagination_response.data.decode("GBK").encode("UTF-8")
    # 获取图片地址
    image_info_html = tool.find_sub_string(photo_pagination_html, '<div class="zzz">', "</div>")
    if not image_info_html:
        raise robot.RobotException("页面截取图片列表失败\n%s" % photo_pagination_html)
    image_url_list = re.findall('<img src="([^"]*)"', image_info_html)
    if len(image_url_list) == 0:
        raise robot.RobotException("页面匹配图片地址失败\n%s" % image_info_html)
    for image_url in image_url_list:
        result["image_url_list"].append("http://www.88mmw.com" + str(image_url).replace("-lp", ""))
    # 判断是不是最后一页
    max_page_count = tool.find_sub_string(photo_pagination_html, '<div class="page"><span>共 <strong>', '</strong> 页')
    if not max_page_count:
        result['is_over'] = True
    elif robot.is_integer(max_page_count):
        result['is_over'] = page_count >= int(max_page_count)
    return result


class Gallery(robot.Robot):
    def __init__(self):
        global IMAGE_DOWNLOAD_PATH
        global NEW_SAVE_DATA_PATH

        sys_config = {
            robot.SYS_DOWNLOAD_IMAGE: True,
            robot.SYS_NOT_CHECK_SAVE_DATA: True,
        }
        robot.Robot.__init__(self, sys_config)

        # 设置全局变量，供子线程调用
        IMAGE_DOWNLOAD_PATH = self.image_download_path
        NEW_SAVE_DATA_PATH = robot.get_new_save_file_path(self.save_data_path)

    def main(self):
        # sub_path  last_page_id
        account_list = robot.read_save_data(self.save_data_path, 0, ["", "0"])
        for sub_path in SUB_PATH_LIST:
            if sub_path not in account_list:
                account_list[sub_path] = [sub_path, "0"]

        # 循环下载每个id
        main_thread_count = threading.activeCount()
        for sub_path in account_list:
            # 检查正在运行的线程数
            while threading.activeCount() >= self.thread_count + main_thread_count:
                if robot.is_process_end() == 0:
                    time.sleep(10)
                else:
                    break

            # 提前结束
            if robot.is_process_end() > 0:
                break

            # 开始下载
            thread = Download(account_list[sub_path], self.thread_lock)
            thread.start()

            time.sleep(1)

        # 检查除主线程外的其他所有线程是不是全部结束了
        while threading.activeCount() > main_thread_count:
            time.sleep(10)

        # 未完成的数据保存
        if len(ACCOUNTS) > 0:
            new_save_data_file = open(NEW_SAVE_DATA_PATH, "a")
            for account_id in ACCOUNTS:
                new_save_data_file.write("\t".join(account_list[account_id]) + "\n")
            new_save_data_file.close()

        # 删除临时文件夹
        self.finish_task()

        # 重新排序保存存档文件
        robot.rewrite_save_file(NEW_SAVE_DATA_PATH, self.save_data_path)

        log.step("全部下载完毕，耗时%s秒，共计图片%s张" % (self.get_run_time(), TOTAL_IMAGE_COUNT))


class Download(threading.Thread):
    def __init__(self, account_info, thread_lock):
        threading.Thread.__init__(self)
        self.account_info = account_info
        self.thread_lock = thread_lock

    def run(self):
        global TOTAL_IMAGE_COUNT

        sub_path = self.account_info[0]

        try:
            log.step(sub_path + " 开始")

            page_count = 1
            total_image_count = 0
            is_over = False
            first_page_id = None
            while not is_over:
                log.step(sub_path + " 开始解析第%s页图集" % page_count)

                # 获取相册
                try:
                    album_pagination_response = get_one_page_album(sub_path, page_count)
                except robot.RobotException, e:
                    log.error(sub_path + " 第%s页图集解析失败，原因：%s" % (page_count, e.message))
                    raise

                log.trace(sub_path + " 第%s页解析的所有图集：%s" % (page_count, album_pagination_response["album_info_list"]))

                for album_info in album_pagination_response["album_info_list"]:
                    # 检查是否达到存档记录
                    if int(album_info["page_id"]) <= int(self.account_info[1]):
                        is_over = True
                        break

                    # 新的存档记录
                    if first_page_id is None:
                        first_page_id = album_info["page_id"]

                    album_page_count = 1
                    image_count = 1
                    album_path = os.path.join(IMAGE_DOWNLOAD_PATH, sub_path, album_info["album_title"])
                    while True:
                        try:
                            photo_pagination_response = get_one_page_photo(sub_path, album_info["page_id"], album_page_count)
                        except robot.RobotException, e:
                            log.error(sub_path + " %s号图集第%s页解析失败，原因：%s" % (album_info["page_id"], album_page_count, e.message))
                            raise
                        except SystemExit:
                            log.step("提前退出")
                            raise

                        log.trace(sub_path + " %s号图集第%s页解析的所有图集：%s" % (album_info["page_id"], album_page_count, album_pagination_response["album_info_list"]))

                        for image_url in photo_pagination_response["image_url_list"]:
                            log.step(sub_path + " %s号图集 开始下载第%s张图片 %s" % (album_info["page_id"], image_count, image_url))

                            file_type = image_url.split(".")[-1]
                            file_path = os.path.join(album_path, "%03d.%s" % (image_count, file_type))
                            save_file_return = net.save_net_file(image_url, file_path)
                            if save_file_return["status"] == 1:
                                log.step(sub_path + " %s号图集 第%s张图片下载成功" % (album_info["page_id"], image_count))
                                image_count += 1
                            else:
                                 log.error(sub_path + " %s号图集 第%s张图片 %s 下载失败，原因：%s" % (album_info["page_id"], image_count, image_url, robot.get_save_net_file_failed_reason(save_file_return["code"])))

                        if is_over or photo_pagination_response["is_over"]:
                            break
                        else:
                            album_page_count += 1

                    if is_over:
                        break
                    else:
                        total_image_count += image_count

                if not is_over:
                    if album_pagination_response["is_over"]:
                        break
                    else:
                        page_count += 1

                log.step(sub_path + " 下载完毕，总共获得%s张图片" % (total_image_count - 1))

            # 新的存档记录
            if first_page_id is not None:
                self.account_info[1] = first_page_id

            # 保存最后的信息
            tool.write_file("\t".join(self.account_info), NEW_SAVE_DATA_PATH)
            self.thread_lock.acquire()
            TOTAL_IMAGE_COUNT += total_image_count
            ACCOUNTS.remove(sub_path)
            self.thread_lock.release()

            log.step(sub_path + " 完成")

        except SystemExit, se:
            if se.code == 0:
                log.step(sub_path + " 提前退出")
            else:
                log.error(sub_path + " 异常退出")
        except Exception, e:
            log.error(sub_path + " 未知异常")
            log.error(str(e) + "\n" + str(traceback.format_exc()))


if __name__ == "__main__":
    Gallery().main()
