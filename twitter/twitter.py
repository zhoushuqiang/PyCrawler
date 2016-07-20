# -*- coding:UTF-8  -*-
"""
Twitter图片爬虫
@author: hikaru
email: hikaru870806@hotmail.com
如有问题或建议请联系
"""
from common import log, robot, tool
import json
import os
import re
import threading
import time
import traceback
import urllib2

ACCOUNTS = []
INIT_MAX_ID = "999999999999999999"
TOTAL_IMAGE_COUNT = 0
TOTAL_VIDEO_COUNT = 0
GET_IMAGE_COUNT = 0
GET_VIDEO_COUNT = 0
IMAGE_TEMP_PATH = ""
IMAGE_DOWNLOAD_PATH = ""
VIDEO_TEMP_PATH = ""
VIDEO_DOWNLOAD_PATH = ""
NEW_SAVE_DATA_PATH = ""
IS_SORT = 1
IS_DOWNLOAD_IMAGE = 1
IS_DOWNLOAD_VIDEO = 1

threadLock = threading.Lock()


def print_error_msg(msg):
    threadLock.acquire()
    log.error(msg)
    threadLock.release()


def print_step_msg(msg):
    threadLock.acquire()
    log.step(msg)
    threadLock.release()


def trace(msg):
    threadLock.acquire()
    log.trace(msg)
    threadLock.release()


# 获取当前cookies对应的authenticity_token
def get_authenticity_token():
    index_url = "https://twitter.com"
    index_return_code, index_page = tool.http_request(index_url)[:2]
    if index_return_code:
        authenticity_token_find = re.findall('value="([^"]*)" name="authenticity_token"', index_page)
        if len(authenticity_token_find) == 1:
            return authenticity_token_find[0]
    return None


# 根据账号名字获得账号id（字母账号->数字账号)
def get_account_id(account_name):
    account_index_url = "https://twitter.com/" + account_name
    account_index_return_code, account_index_page = tool.http_request(account_index_url)[:2]
    if account_index_return_code == 1:
        account_id_find = re.findall('<div class="ProfileNav" role="navigation" data-user-id="([^"]*)">', account_index_page)
        if len(account_id_find) == 1:
            return account_id_find[0]
    return None


# 关注指定账号（无效）
def follow_account(authenticity_token, account_id):
    follow_url = "https://twitter.com/i/user/follow"
    follow_data = {"authenticity_token": authenticity_token, "challenges_passed": False, "handles_challenges": 1,
                   "user_id": account_id}
    follow_return_code, follow_data = tool.http_request(follow_url, follow_data)[:2]
    if follow_return_code == 1:
        return True
    return False


# 取消关注指定账号（无效）
def unfollow_account(authenticity_token, account_id):
    unfollow_url = "https://twitter.com/i/user/follow"
    unfollow_data = {"authenticity_token": authenticity_token, "challenges_passed": False, "handles_challenges": 1,
                     "user_id": account_id}
    unfollow_return_code, unfollow_data = tool.http_request(unfollow_url, unfollow_data)[:2]
    if unfollow_return_code == 1:
        return True
    return False


# 获取指定账号的全部关注列表（需要登录）
def get_twitter_follow_list(account_name):
    position_id = "2000000000000000000"
    follow_list = []
    while True:
        follow_page_data = get_twitter_follow_page_data(account_name, position_id)
        if follow_page_data is not None:
            profile_list = re.findall('<div class="ProfileCard[^>]*data-screen-name="([^"]*)"[^>]*>', follow_page_data["items_html"])
            if len(profile_list) > 0:
                follow_list += profile_list
            if follow_page_data["has_more_items"]:
                position_id = follow_page_data["min_position"]
            else:
                break
        else:
            break
    return follow_list


# 获取指定一页的关注列表
def get_twitter_follow_page_data(account_name, position_id):
    follow_list_url = "https://twitter.com/%s/following/users?max_position=%s" % (account_name, position_id)
    follow_list_return_code, follow_list_data = tool.http_request(follow_list_url)[:2]
    if follow_list_return_code == 1:
        try:
            follow_list_data = json.loads(follow_list_data)
        except ValueError:
            pass
        else:
            if robot.check_sub_key(("min_position", "has_more_items", "items_html"), follow_list_data):
                return follow_list_data
    return None


# 获取一页的媒体信息
def get_twitter_media_page_data(account_name, data_tweet_id):
    media_page_url = "https://twitter.com/i/profiles/show/%s/media_timeline" % account_name
    media_page_url += "?include_available_features=1&include_entities=1&max_position=%s" % data_tweet_id
    media_page_return_code, media_page_response = tool.http_request(media_page_url)[:2]
    if media_page_return_code == 1:
        try:
            media_page = json.loads(media_page_response)
        except ValueError:
            pass
        else:
            if robot.check_sub_key(("has_more_items", "items_html", "min_position"), media_page):
                return media_page
    return None


# 从媒体列表中将不同的媒体信息拆分组
def get_tweet_list(media_page_items_html):
    media_page_items_html = media_page_items_html.replace('\n', "").replace('<li class="js-stream-item stream-item stream-item"', '\n<li class="js-stream-item stream-item stream-item"')
    tweet_data_list = media_page_items_html.split("\n")
    tweet_id_list = []
    for tweet_data in tweet_data_list:
        if len(tweet_data) < 50:
            continue
        tweet_data = tweet_data.encode("utf-8")
        # 被圈出来的用户，追加到前面的页面中
        if tweet_data.find('<span class="button-text following-text">') >= 0:
            tweet_id_list[-1] += tweet_data
        else:
            tweet_id_list.append(tweet_data)
    return tweet_id_list


# 获取视频的真实下载地址（ts文件列表）
def get_video_source_url(tweet_id):
    # video_page_url = "https://twitter.com/i/videos/tweet/%s?embed_source=clientlib&player_id=1&rpc_init=1&conviva_environment=test" % tweet_id
    video_page_url = "https://twitter.com/i/videos/tweet/" + tweet_id
    video_page_return_code, video_page = tool.http_request(video_page_url)[:2]
    if video_page_return_code == 1:
        m3u8_file_find = re.findall("&quot;video_url&quot;:&quot;([^&]*)&quot;", video_page)
        if len(m3u8_file_find) == 1:
            m3u8_file_url = m3u8_file_find[0].replace("\\/", "/")
            ts_file_list = []
            deal_m3u8_file(m3u8_file_url, ts_file_list)
            return ts_file_list
    return []


# https://video.twimg.com/ext_tw_video/749759483224600577/pu/pl/DzYugRHcg3WVgeWY.m3u8
# 迭代从m3u8文件中获取真实的ts地址列表
def deal_m3u8_file(file_url, ts_file_list):
    file_return_code, file_data = tool.http_request(file_url)[:2]
    if file_return_code == 1:
        new_file_url_list = re.findall("(/ext_tw_video/[\S]*)", file_data)
        print "find list" + str(new_file_url_list)
        for new_file_url in new_file_url_list:
            new_file_url = "https://video.twimg.com" + new_file_url
            if new_file_url.split(".")[-1] == "m3u8":
                deal_m3u8_file(new_file_url, ts_file_list)
            elif new_file_url.split(".")[-1] == "ts":
                ts_file_list.append(new_file_url)


# 将多个ts文件的地址保存为本地视频文件
def save_video(ts_file_list, file_path):
    file_handle = open(file_path, 'wb')
    for ts_file_url in ts_file_list:
        ts_file_return_code, ts_file_data = tool.http_request(ts_file_url)[:2]
        if ts_file_return_code == 1:
            file_handle.write(ts_file_data)
        else:
            return False
    file_handle.close()
    return True


# 返回的是当前时区对应的时间
def get_image_last_modified(response):
    if isinstance(response, urllib2.addinfourl):
        info = response.info()
        last_modified_time = tool.get_response_info(info, "last-modified")
        last_modified_time = time.strptime(last_modified_time, "%a, %d %b %Y %H:%M:%S %Z")
        return int(time.mktime(last_modified_time)) - time.timezone
    return 0


# 将图片的二进制数据保存为本地文件
def save_image(image_byte, image_path):
    image_path = tool.change_path_encoding(image_path)
    image_file = open(image_path, "wb")
    image_file.write(image_byte)
    image_file.close()


class Twitter(robot.Robot):
    def __init__(self, save_data_path="", this_image_download_path="", this_image_temp_path="",
                 this_video_download_path="", this_video_temp_path=""):
        global GET_IMAGE_COUNT
        global GET_VIDEO_COUNT
        global IMAGE_TEMP_PATH
        global IMAGE_DOWNLOAD_PATH
        global VIDEO_TEMP_PATH
        global VIDEO_DOWNLOAD_PATH
        global NEW_SAVE_DATA_PATH
        global IS_SORT
        global IS_DOWNLOAD_IMAGE
        global IS_DOWNLOAD_VIDEO

        robot.Robot.__init__(self)

        if save_data_path != "":
            self.save_data_path = save_data_path

        GET_IMAGE_COUNT = self.get_image_count
        GET_VIDEO_COUNT = self.get_video_count
        if this_image_temp_path != "":
            IMAGE_TEMP_PATH = this_image_temp_path
        else:
            IMAGE_TEMP_PATH = self.image_temp_path
        if this_image_download_path != "":
            IMAGE_DOWNLOAD_PATH = this_image_download_path
        else:
            IMAGE_DOWNLOAD_PATH = self.image_download_path
        if this_video_temp_path != "":
            VIDEO_TEMP_PATH = this_video_temp_path
        else:
            VIDEO_TEMP_PATH = self.video_temp_path
        if this_video_download_path != "":
            VIDEO_DOWNLOAD_PATH = this_video_download_path
        else:
            VIDEO_DOWNLOAD_PATH = self.video_download_path
        IS_SORT = self.is_sort
        IS_DOWNLOAD_IMAGE = self.is_download_image
        IS_DOWNLOAD_VIDEO = self.is_download_video
        NEW_SAVE_DATA_PATH = robot.get_new_save_file_path(self.save_data_path)

        tool.print_msg("配置文件读取完成")

    def main(self):
        global ACCOUNTS
        
        if IS_DOWNLOAD_IMAGE == 0:
            print_error_msg("下载图片没开启，请检查配置！")
            tool.process_exit()

        start_time = time.time()

        # 图片保存目录
        print_step_msg("创建图片根目录：" + IMAGE_DOWNLOAD_PATH)
        if not tool.make_dir(IMAGE_DOWNLOAD_PATH, 0):
            print_error_msg("创建图片根目录：" + IMAGE_DOWNLOAD_PATH + " 失败")
            tool.process_exit()

        # 设置代理
        if self.is_proxy == 1 or self.is_proxy == 2:
            tool.set_proxy(self.proxy_ip, self.proxy_port, "https")

        # 寻找idlist，如果没有结束进程
        account_list = {}
        if os.path.exists(self.save_data_path):
            # account_name  image_count  last_image_time
            account_list = robot.read_save_data(self.save_data_path, 0, ["", "0", "0", "0"])
            ACCOUNTS = account_list.keys()
        else:
            print_error_msg("用户ID存档文件: " + self.save_data_path + "不存在")
            tool.process_exit()

        # 创建临时存档文件
        new_save_data_file = open(NEW_SAVE_DATA_PATH, "w")
        new_save_data_file.close()

        # 启用线程监控是否需要暂停其他下载线程
        process_control_thread = tool.ProcessControl()
        process_control_thread.setDaemon(True)
        process_control_thread.start()

        # 循环下载每个id
        main_thread_count = threading.activeCount()
        for account_name in sorted(account_list.keys()):
            # 检查正在运行的线程数
            while threading.activeCount() >= self.thread_count + main_thread_count:
                if tool.is_process_end() == 0:
                    time.sleep(10)
                else:
                    break

            # 提前结束
            if tool.is_process_end() > 0:
                break

            # 开始下载
            thread = Download(account_list[account_name])
            thread.start()

            time.sleep(1)

        # 检查除主线程外的其他所有线程是不是全部结束了
        while threading.activeCount() > main_thread_count:
            time.sleep(10)

        # 未完成的数据保存
        if len(ACCOUNTS) > 0:
            new_save_data_file = open(NEW_SAVE_DATA_PATH, "a")
            for account_name in ACCOUNTS:
                # account_name  image_count  last_image_time
                new_save_data_file.write("\t".join(account_list[account_name]) + "\n")
            new_save_data_file.close()

        # 删除临时文件夹
        tool.remove_dir(IMAGE_TEMP_PATH)

        # 重新排序保存存档文件
        account_list = robot.read_save_data(NEW_SAVE_DATA_PATH, 0, [])
        temp_list = [account_list[key] for key in sorted(account_list.keys())]
        tool.write_file(tool.list_to_string(temp_list), self.save_data_path, 2)
        os.remove(NEW_SAVE_DATA_PATH)

        duration_time = int(time.time() - start_time)
        print_step_msg("全部下载完毕，耗时" + str(duration_time) + "秒，共计图片" + str(TOTAL_IMAGE_COUNT) + "张，视频" + str(TOTAL_VIDEO_COUNT) + "个")


class Download(threading.Thread):
    def __init__(self, account_info):
        threading.Thread.__init__(self)
        self.account_info = account_info

    def run(self):
        global TOTAL_IMAGE_COUNT
        global TOTAL_VIDEO_COUNT

        account_name = self.account_info[0]

        try:
            print_step_msg(account_name + " 开始")

            # 如果需要重新排序则使用临时文件夹，否则直接下载到目标目录
            if IS_SORT == 1:
                image_path = os.path.join(IMAGE_TEMP_PATH, account_name)
                video_path = os.path.join(VIDEO_TEMP_PATH, account_name)
            else:
                image_path = os.path.join(IMAGE_DOWNLOAD_PATH, account_name)
                video_path = os.path.join(VIDEO_DOWNLOAD_PATH, account_name)

            image_count = 1
            video_count = 1
            data_tweet_id = INIT_MAX_ID
            first_tweet_id = "0"
            is_over = False
            need_make_image_dir = True
            need_make_video_dir = True
            while not is_over:
                # 获取指定时间点后的一页图片信息
                media_page = get_twitter_media_page_data(account_name, data_tweet_id)
                if media_page is None:
                    print_error_msg(account_name + " 媒体列表解析异常")
                    break

                tweet_list = get_tweet_list(media_page["items_html"])
                if len(tweet_list) == 0:
                    print_error_msg(account_name + " 媒体列表拆分异常，items_html：" + str(media_page["items_html"]))
                    break

                for tweet_data in tweet_list:
                    tweet_id_find = re.findall('data-tweet-id="([\d]*)"', tweet_data)
                    if len(tweet_id_find) != 1:
                        print_error_msg(account_name + " tweet id解析异常，tweet数据：" + tweet_data)
                        continue

                    tweet_id = str(tweet_id_find[0])
                    # 将第一个tweet的id做为新的存档记录
                    if first_tweet_id == "0":
                        first_tweet_id = tweet_id
                    # 检查是否tweet的id小于上次的记录
                        if int(tweet_id) <= int(self.account_info[3]):
                            is_over = True
                            break

                    # 视频
                    if IS_DOWNLOAD_VIDEO == 1:
                        # 这个tweet是否包含视频7
                        if tweet_data.find("PlayableMedia--video") >= 0:
                            video_url_list = get_video_source_url(tweet_id)
                            if len(video_url_list) == 0:
                                print_error_msg(account_name + " 第" + str(video_count) + "个视频没有获取到源地址，tweet id：" + tweet_id)
                                continue

                            # 第一个视频，创建目录
                            if need_make_video_dir:
                                if not tool.make_dir(video_path, 0):
                                    print_error_msg(account_name + " 创建图片下载目录： " + video_path + " 失败")
                                    tool.process_exit()
                                need_make_video_dir = False

                            # 将域名拼加起来
                            video_file_path = os.path.join(video_path, str("%04d" % video_count) + ".ts")
                            print_step_msg(account_name + " 开始下载第" + str(video_count) + "个视频：" + str(video_url_list))
                            if save_video(video_url_list, video_file_path):
                                print_step_msg(account_name + " 第" + str(video_count) + "个视频下载成功")
                                video_count += 1
                            else:
                                print_error_msg(account_name + " 第" + str(video_count) + "个视频 " + str(video_url_list) + " 下载失败")

                            # 达到配置文件中的下载数量，结束
                            if 0 < GET_VIDEO_COUNT < video_count:
                                is_over = True

                    # 图片
                    if IS_DOWNLOAD_IMAGE == 1:
                        # 匹配获取全部的图片地址
                        image_url_list = re.findall('data-image-url="([^"]*)"', tweet_data)
                        for image_url in image_url_list:
                            image_url = str(image_url)
                            print_step_msg(account_name + " 开始下载第 " + str(image_count) + "张图片：" + image_url)

                            image_return_code, image_byte = tool.http_request(image_url)[:2]
                            # 404，不算做错误，图片已经被删掉了
                            if image_return_code == -404:
                                print_error_msg(account_name + " 第" + str(image_count) + "张图片 " + image_url + "已被删除，跳过")
                            elif image_return_code == 1:
                                file_type = image_url.split(".")[-1].split(":")[0]
                                image_file_path = os.path.join(image_path, str("%04d" % image_count) + "." + file_type)
                                # 第一张图片，创建目录
                                if need_make_image_dir:
                                    if not tool.make_dir(image_path, 0):
                                        print_error_msg(account_name + " 创建图片下载目录： " + image_path + " 失败")
                                        tool.process_exit()
                                    need_make_image_dir = False
                                save_image(image_byte, image_file_path)
                                print_step_msg(account_name + " 第" + str(image_count) + "张图片下载成功")
                                image_count += 1
                            else:
                                print_error_msg(account_name + " 第" + str(image_count) + "张图片 " + image_url + " 获取失败")

                        # 达到配置文件中的下载数量，结束
                        if 0 < GET_IMAGE_COUNT < image_count:
                            is_over = True

                    if is_over:
                        break

                if not is_over:
                    # 查找下一页的data_tweet_id
                    if media_page["has_more_items"]:
                        data_tweet_id = str(media_page["min_position"])
                    else:
                        is_over = True

            print_step_msg(account_name + " 下载完毕，总共获得" + str(image_count - 1) + "张图片和" + str(video_count - 1) + "个视频")

            # 排序
            if IS_SORT == 1:
                if image_count > 1:
                    destination_path = os.path.join(IMAGE_DOWNLOAD_PATH, account_name)
                    if robot.sort_file(image_path, destination_path, int(self.account_info[1]), 4):
                        print_step_msg(account_name + " 图片从下载目录移动到保存目录成功")
                    else:
                        print_error_msg(account_name + " 创建图片子目录： " + destination_path + " 失败")
                        tool.process_exit()
                if video_count > 1:
                    destination_path = os.path.join(VIDEO_DOWNLOAD_PATH, account_name)
                    if robot.sort_file(video_path, destination_path, int(self.account_info[2]), 4):
                        print_step_msg(account_name + " 视频从下载目录移动到保存目录成功")
                    else:
                        print_error_msg(account_name + " 创建视频保存目录： " + destination_path + " 失败")
                        tool.process_exit()

            # 新的存档记录
            if first_tweet_id != "0":
                self.account_info[1] = str(int(self.account_info[1]) + image_count - 1)
                self.account_info[2] = str(int(self.account_info[2]) + video_count - 1)
                self.account_info[3] = first_tweet_id

            # 保存最后的信息
            threadLock.acquire()
            tool.write_file("\t".join(self.account_info), NEW_SAVE_DATA_PATH)
            TOTAL_IMAGE_COUNT += image_count - 1
            TOTAL_VIDEO_COUNT += video_count - 1
            ACCOUNTS.remove(account_name)
            threadLock.release()

            print_step_msg(account_name + " 完成")
        except SystemExit, se:
            if se.code == 0:
                print_step_msg(account_name + " 提前退出")
            else:
                print_error_msg(account_name + " 异常退出")
        except Exception, e:
            print_error_msg(account_name + " 未知异常")
            print_error_msg(str(e) + "\n" + str(traceback.format_exc()))


if __name__ == "__main__":
    Twitter().main()
