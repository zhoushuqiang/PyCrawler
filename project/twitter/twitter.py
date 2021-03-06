# -*- coding:UTF-8  -*-
"""
Twitter图片&视频爬虫
https://twitter.com/
@author: hikaru
email: hikaru870806@hotmail.com
如有问题或建议请联系
"""
from common import *
import os
import re
import threading
import time
import traceback
import urllib

COOKIE_INFO = {}


# 根据账号名字获得账号id（字母账号->数字账号)
def get_account_index_page(account_name):
    account_index_url = "https://twitter.com/%s" % account_name
    account_index_response = net.http_request(account_index_url, method="GET", cookies_list=COOKIE_INFO)
    result = {
        "account_id": None,  # account id
    }
    if account_index_response.status == 404:
        raise crawler.CrawlerException("账号不存在")
    elif account_index_response.status != net.HTTP_RETURN_CODE_SUCCEED:
        raise crawler.CrawlerException(crawler.request_failre(account_index_response.status))
    if account_index_response.data.find('<div class="ProtectedTimeline">') >= 0:
        raise crawler.CrawlerException("私密账号，需要关注才能访问")
    account_id = tool.find_sub_string(account_index_response.data, '<div class="ProfileNav" role="navigation" data-user-id="', '">')
    if not crawler.is_integer(account_id):
        raise crawler.CrawlerException("页面截取用户id失败\n%s" % account_index_response.data)
    result["account_id"] = account_id
    return result


# 获取一页的媒体信息
def get_one_page_media(account_name, position_blog_id):
    media_pagination_url = "https://twitter.com/i/profiles/show/%s/media_timeline" % account_name
    query_data = {
        "include_available_features": "1",
        "include_entities": "1",
        "max_position": position_blog_id,
    }
    media_pagination_response = net.http_request(media_pagination_url, method="GET", fields=query_data, cookies_list=COOKIE_INFO, json_decode=True)
    result = {
        "is_error": False,  # 是不是格式不符合
        "is_over": False,  # 是不是已经最后一页媒体（没有获取到任何内容）
        "media_info_list": [],  # 全部媒体信息
        "next_page_position": None  # 下一页指针
    }
    if media_pagination_response.status != net.HTTP_RETURN_CODE_SUCCEED:
        raise crawler.CrawlerException(crawler.request_failre(media_pagination_response.status))
    if not crawler.check_sub_key(("has_more_items",), media_pagination_response.json_data):
        raise crawler.CrawlerException("返回信息'has_more_items'字段不存在\n%s" % media_pagination_response.json_data)
    if not crawler.check_sub_key(("items_html",), media_pagination_response.json_data):
        raise crawler.CrawlerException("返回信息'items_html'字段不存在\n%s" % media_pagination_response.json_data)
    if not crawler.check_sub_key(("new_latent_count",), media_pagination_response.json_data):
        raise crawler.CrawlerException("返回信息'new_latent_count'字段不存在\n%s" % media_pagination_response.json_data)
    if not crawler.is_integer(media_pagination_response.json_data["new_latent_count"]):
        raise crawler.CrawlerException("返回信息'new_latent_count'字段类型不正确\n%s" % media_pagination_response.json_data)
    if not crawler.check_sub_key(("min_position",), media_pagination_response.json_data):
        raise crawler.CrawlerException("返回信息'min_position'字段不存在\n%s" % media_pagination_response.json_data)
    if not crawler.is_integer(media_pagination_response.json_data["min_position"]) and media_pagination_response.json_data["min_position"] is not None:
        raise crawler.CrawlerException("返回信息'min_position'字段类型不正确\n%s" % media_pagination_response.json_data)
    # 没有任何内容
    if int(media_pagination_response.json_data["new_latent_count"]) == 0 and not str(media_pagination_response.json_data["items_html"]).strip():
        result["is_skip"] = True
        return result
    # tweet信息分组
    temp_tweet_data_list = media_pagination_response.json_data["items_html"].replace("\n", "").replace('<li class="js-stream-item stream-item stream-item"', '\n<li class="js-stream-item stream-item stream-item"').split("\n")
    tweet_data_list = []
    for tweet_data in temp_tweet_data_list:
        if len(tweet_data) < 50:
            continue
        tweet_data = tweet_data.encode("UTF-8")
        # 被圈出来的用户，追加到前面的页面中
        if tweet_data.find('<div class="account  js-actionable-user js-profile-popup-actionable') >= 0:
            tweet_data_list[-1] += tweet_data
        else:
            tweet_data_list.append(tweet_data)
    if len(tweet_data_list) == 0:
        raise crawler.CrawlerException("tweet分组失败\n%s" % media_pagination_response.json_data["items_html"])
    if int(media_pagination_response.json_data["new_latent_count"]) != len(tweet_data_list):
        raise crawler.CrawlerException("tweet分组数量和返回数据中不一致\n%s\n%s" % (media_pagination_response.json_data["items_html"], media_pagination_response.json_data["new_latent_count"]))
    for tweet_data in tweet_data_list:
        result_media_info = {
            "blog_id": None,  # 日志id
            "has_video": False,  # 是不是包含视频
            "image_url_list": [],  # 全部图片地址
        }
        # 获取日志id
        blog_id = tool.find_sub_string(tweet_data, 'data-tweet-id="', '"')
        if not crawler.is_integer(blog_id):
            raise crawler.CrawlerException("tweet内容中截取tweet id失败\n%s" % tweet_data)
        result_media_info["blog_id"] = str(blog_id)
        # 获取图片地址
        image_url_list = re.findall('data-image-url="([^"]*)"', tweet_data)
        result_media_info["image_url_list"] = map(str, image_url_list)
        # 判断是不是有视频
        result_media_info["has_video"] = tweet_data.find("PlayableMedia--video") >= 0
        result["media_info_list"].append(result_media_info)
    # 判断是不是还有下一页
    if media_pagination_response.json_data["has_more_items"]:
        result["next_page_position"] = str(media_pagination_response.json_data["min_position"])
    return result


# 根据视频所在推特的ID，获取视频的下载地址
def get_video_play_page(tweet_id):
    video_play_url = "https://twitter.com/i/videos/tweet/%s" % tweet_id
    video_play_response = net.http_request(video_play_url, method="GET", cookies_list=COOKIE_INFO)
    result = {
        "video_url": None,  # 视频地址
    }
    if video_play_response.status != net.HTTP_RETURN_CODE_SUCCEED:
        raise crawler.CrawlerException(crawler.request_failre(video_play_response.status))
    # 包含m3u8文件地址的处理
    # https://video.twimg.com/ext_tw_video/749759483224600577/pu/pl/DzYugRHcg3WVgeWY.m3u8
    m3u8_file_url = tool.find_sub_string(video_play_response.data, "&quot;video_url&quot;:&quot;", ".m3u8&quot;")
    if m3u8_file_url:
        m3u8_file_url = m3u8_file_url.replace("\\/", "/") + ".m3u8"
        file_url_protocol, file_url_path = urllib.splittype(m3u8_file_url)
        file_url_host = urllib.splithost(file_url_path)[0]
        m3u8_file_response = net.http_request(m3u8_file_url, method="GET")
        if m3u8_file_response.status != net.HTTP_RETURN_CODE_SUCCEED:
            raise crawler.CrawlerException("m3u8文件 %s 解析失败，%s" % (m3u8_file_url, crawler.request_failre(m3u8_file_response.status)))
        # 是否包含的是m3u8文件（不同分辨率）
        include_m3u8_file_list = re.findall("(/[\S]*.m3u8)", m3u8_file_response.data)
        if len(include_m3u8_file_list) > 0:
            # 生成最高分辨率视频所在的m3u8文件地址
            m3u8_file_url = "%s://%s%s" % (file_url_protocol, file_url_host, include_m3u8_file_list[-1])
            m3u8_file_response = net.http_request(m3u8_file_url, method="GET")
            if m3u8_file_response.status != net.HTTP_RETURN_CODE_SUCCEED:
                raise crawler.CrawlerException("最高分辨率m3u8文件 %s 解析失败，%s" % (m3u8_file_url, crawler.request_failre(m3u8_file_response.status)))
        # 包含分P视频文件名的m3u8文件
        ts_url_find = re.findall("(/[\S]*.ts)", m3u8_file_response.data)
        if len(ts_url_find) == 0:
            raise crawler.CrawlerException("m3u8文件截取视频地址失败\n%s\n%s" % (m3u8_file_url, m3u8_file_response.data))
        result["video_url"] = []
        for ts_file_path in ts_url_find:
            result["video_url"].append("%s://%s%s" % (file_url_protocol, file_url_host, str(ts_file_path)))
    else:
        # 直接包含视频播放地址的处理
        video_url = tool.find_sub_string(video_play_response.data, "&quot;video_url&quot;:&quot;", "&quot;")
        if video_url:
            result["video_url"] = video_url.replace("\\/", "/")
        else:
            # 直接包含视频播放地址的处理
            vmap_file_url = tool.find_sub_string(video_play_response.data, "&quot;vmap_url&quot;:&quot;", "&quot;")
            if not vmap_file_url:
                raise crawler.CrawlerException("页面截取视频播放地址失败\n%s" % video_play_response.data)
            vmap_file_url = vmap_file_url.replace("\\/", "/")
            vmap_file_response = net.http_request(vmap_file_url, method="GET")
            if vmap_file_response.status != net.HTTP_RETURN_CODE_SUCCEED:
                raise crawler.CrawlerException("视频播放页 %s 解析失败\n%s" % (vmap_file_url, crawler.request_failre(vmap_file_response.status)))
            video_url = tool.find_sub_string(vmap_file_response.data, "<![CDATA[", "]]>")
            if not video_url:
                raise crawler.CrawlerException("视频播放页 %s 截取视频地址失败\n%s" % (vmap_file_url, video_play_response.data))
            result["video_url"] = str(video_url.replace("\\/", "/"))
    return result


class Twitter(crawler.Crawler):
    def __init__(self, extra_config=None):
        global COOKIE_INFO

        sys_config = {
            crawler.SYS_DOWNLOAD_IMAGE: True,
            crawler.SYS_DOWNLOAD_VIDEO: True,
            crawler.SYS_SET_PROXY: True,
            crawler.SYS_GET_COOKIE: {".twitter.com": ()}
        }
        crawler.Crawler.__init__(self, sys_config, extra_config)

        # 设置全局变量，供子线程调用
        COOKIE_INFO = self.cookie_value

        # 解析存档文件
        # account_name  image_count  last_image_time
        self.account_list = crawler.read_save_data(self.save_data_path, 0, ["", "", "0", "0", "0"])

    def main(self):
        # 循环下载每个id
        main_thread_count = threading.activeCount()
        for account_name in sorted(self.account_list.keys()):
            # 检查正在运行的线程数
            if threading.activeCount() >= self.thread_count + main_thread_count:
                self.wait_sub_thread()

            # 提前结束
            if not self.is_running():
                break

            # 开始下载
            thread = Download(self.account_list[account_name], self)
            thread.start()

            time.sleep(1)

        # 检查除主线程外的其他所有线程是不是全部结束了
        while threading.activeCount() > main_thread_count:
            self.wait_sub_thread()

        # 未完成的数据保存
        if len(self.account_list) > 0:
            tool.write_file(tool.list_to_string(self.account_list.values()), self.temp_save_data_path)

        # 重新排序保存存档文件
        crawler.rewrite_save_file(self.temp_save_data_path, self.save_data_path)

        log.step("全部下载完毕，耗时%s秒，共计图片%s张，视频%s个" % (self.get_run_time(), self.total_image_count, self.total_video_count))


class Download(crawler.DownloadThread):
    init_position_blog_id = "999999999999999999"

    def __init__(self, account_info, main_thread):
        crawler.DownloadThread.__init__(self, account_info, main_thread)
        self.account_name = self.account_info[0]
        log.step(self.account_name + " 开始")

    # 获取所有可下载媒体
    def get_crawl_list(self):
        position_blog_id = self.init_position_blog_id
        media_info_list = []
        is_over = False
        # 获取全部还未下载过需要解析的媒体
        while not is_over:
            self.main_thread_check()  # 检测主线程运行状态
            log.step(self.account_name + " 开始解析position %s后的一页媒体列表" % position_blog_id)

            # 获取指定时间点后的一页图片信息
            try:
                media_pagination_response = get_one_page_media(self.account_name, position_blog_id)
            except crawler.CrawlerException, e:
                log.error(self.account_name + " position %s后的一页媒体信息解析失败，原因：%s" % (position_blog_id, e.message))
                raise

            if media_pagination_response["is_over"]:
                break

            log.trace(self.account_name + " position %s解析的全部媒体：%s" % (position_blog_id, media_pagination_response["media_info_list"]))

            # 寻找这一页符合条件的媒体
            for media_info in media_pagination_response["media_info_list"]:
                # 检查是否达到存档记录
                if int(media_info["blog_id"]) > int(self.account_info[4]):
                    media_info_list.append(media_info)
                else:
                    is_over = True
                    break

            if not is_over:
                # 下一页的指针
                if media_pagination_response["next_page_position"] is None:
                    is_over = True
                else:
                    # 设置下一页
                    position_blog_id = media_pagination_response["next_page_position"]

        return media_info_list

    # 解析单个媒体
    def crawl_media(self, media_info):
        # 图片下载
        image_index = int(self.account_info[2]) + 1
        if self.main_thread.is_download_image:
            for image_url in media_info["image_url_list"]:
                self.main_thread_check()  # 检测主线程运行状态
                log.step(self.account_name + " 开始下载第%s张图片 %s" % (image_index, image_url))

                file_type = image_url.split(".")[-1].split(":")[0]
                image_file_path = os.path.join(self.main_thread.image_download_path, self.account_name, "%04d.%s" % (image_index, file_type))
                save_file_return = net.save_net_file(image_url, image_file_path)
                if save_file_return["status"] == 1:
                    self.temp_path_list.append(image_file_path)
                    log.step(self.account_name + " 第%s张图片下载成功" % image_index)
                    image_index += 1
                elif save_file_return["status"] == 0 and save_file_return["code"] == 404:
                    log.error(self.account_name + " 第%s张图片 %s 已被删除，跳过" % (image_index, image_url))
                else:
                    log.error(self.account_name + " 第%s张图片 %s 下载失败，原因：%s" % (image_index, image_url, crawler.download_failre(save_file_return["code"])))

        # 视频下载
        video_index = int(self.account_info[3]) + 1
        if self.main_thread.is_download_video and media_info["has_video"]:
            self.main_thread_check()  # 检测主线程运行状态
            # 获取视频播放地址
            try:
                video_play_response = get_video_play_page(media_info["blog_id"])
            except crawler.CrawlerException, e:
                log.error(self.account_name + " 日志%s的视频解析失败，原因：%s" % (media_info["blog_id"], e.message))
                raise

            self.main_thread_check()  # 检测主线程运行状态
            video_url = video_play_response["video_url"]
            log.step(self.account_name + " 开始下载第%s个视频 %s" % (video_index, video_url))

            # 分割后的ts格式视频
            if isinstance(video_url, list):
                video_file_path = os.path.join(self.main_thread.video_download_path, self.account_name, "%04d.ts" % video_index)
                save_file_return = net.save_net_file_list(video_url, video_file_path)
            # 其他格式的视频
            else:
                video_file_type = video_url.split(".")[-1]
                video_file_path = os.path.join(self.main_thread.video_download_path, self.account_name, "%04d.%s" % (video_index, video_file_type))
                save_file_return = net.save_net_file(video_url, video_file_path)
            if save_file_return["status"] == 1:
                self.temp_path_list.append(video_file_path)
                log.step(self.account_name + " 第%s个视频下载成功" % video_index)
                video_index += 1
            else:
                log.error(self.account_name + " 第%s个视频 %s 下载失败" % (video_index, video_url))

        # 媒体内图片和视频全部下载完毕
        self.temp_path_list = []  # 临时目录设置清除
        self.total_image_count += (image_index - 1) - int(self.account_info[2])  # 计数累加
        self.total_video_count += (video_index - 1) - int(self.account_info[3])  # 计数累加
        self.account_info[2] = str(image_index - 1)  # 设置存档记录
        self.account_info[3] = str(video_index - 1)  # 设置存档记录
        self.account_info[4] = media_info["blog_id"]

    def run(self):
        try:
            try:
                account_index_response = get_account_index_page(self.account_name)
            except crawler.CrawlerException, e:
                log.error(self.account_name + " 首页解析失败，原因：%s" % e.message)
                raise

            if self.account_info[1] == "":
                self.account_info[1] = account_index_response["account_id"]
            else:
                if self.account_info[1] != account_index_response["account_id"]:
                    log.error(self.account_name + " account id 不符合，原账号已改名")
                    tool.process_exit()

            # 获取所有可下载媒体
            media_info_list = self.get_crawl_list()
            log.step(self.account_name + " 需要下载的全部媒体解析完毕，共%s个" % len(media_info_list))

            # 从最早的媒体开始下载
            while len(media_info_list) > 0:
                media_info = media_info_list.pop()
                log.step(self.account_name + " 开始解析媒体志 %s" % media_info["blog_id"])
                self.crawl_media(media_info)
                self.main_thread_check()  # 检测主线程运行状态
        except SystemExit, se:
            if se.code == 0:
                log.step(self.account_name + " 提前退出")
            else:
                log.error(self.account_name + " 异常退出")
            # 如果临时目录变量不为空，表示某个日志正在下载中，需要把下载了部分的内容给清理掉
            self.clean_temp_path()
        except Exception, e:
            log.error(self.account_name + " 未知异常")
            log.error(str(e) + "\n" + str(traceback.format_exc()))

        # 保存最后的信息
        with self.thread_lock:
            tool.write_file("\t".join(self.account_info), self.main_thread.temp_save_data_path)
            self.main_thread.total_image_count += self.total_image_count
            self.main_thread.total_video_count += self.total_video_count
            self.main_thread.account_list.pop(self.account_name)
        log.step(self.account_name + " 下载完毕，总共获得%s张图片和%s个视频" % (self.total_image_count, self.total_video_count))
        self.notify_main_thread()


if __name__ == "__main__":
    Twitter().main()
