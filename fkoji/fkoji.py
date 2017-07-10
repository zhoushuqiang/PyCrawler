# -*- coding:UTF-8  -*-
"""
fkoji图片爬虫
http://jigadori.fkoji.com
@author: hikaru
email: hikaru870806@hotmail.com
如有问题或建议请联系
"""
from common import *
from common import BeautifulSoup
import os
import time


# 获取指定页数的所有图片
def get_one_page_photo(page_count):
    photo_pagination_url = "http://jigadori.fkoji.com/?p=%s" % page_count
    return net.http_request(photo_pagination_url)


# 从图片页面中解析获取推特发布时间的时间戳
def get_tweet_created_time(photo_info):
    tweet_created_time_find = photo_info.findAll("div", "tweet-created-at")
    if len(tweet_created_time_find) == 1:
        tweet_created_time_string = tweet_created_time_find[0].text
        return int(time.mktime(time.strptime(tweet_created_time_string, "%Y-%m-%d %H:%M:%S")))
    return None


# 从图片页面中解析获取推特发布账号
def get_tweet_account_id(photo_info):
    span_tags = photo_info.findAll("span")
    for tag in span_tags:
        sub_tag = tag.next.next
        if isinstance(sub_tag, BeautifulSoup.NavigableString):
            if sub_tag.find("@") == 0:
                return sub_tag[1:].encode("GBK")
    return None


class Fkoji(robot.Robot):
    def __init__(self):
        sys_config = {
            robot.SYS_DOWNLOAD_IMAGE: True,
            robot.SYS_SET_PROXY: True,
            robot.SYS_NOT_CHECK_SAVE_DATA: True,
        }
        robot.Robot.__init__(self, sys_config)

    def main(self):
        # 解析存档文件
        last_blog_time = 0
        image_start_index = 0
        if os.path.exists(self.save_data_path):
            save_file = open(self.save_data_path, "r")
            save_info = save_file.read()
            save_file.close()
            save_info = save_info.replace("\n", "").split("\t")
            if len(save_info) >= 2:
                image_start_index = int(save_info[0])
                last_blog_time = int(save_info[1])

        if self.is_sort:
            image_path = self.image_temp_path
        else:
            image_path = self.image_download_path

        if not tool.make_dir(image_path, 0):
            # 图片保存目录创建失败
            self.print_msg("图片下载目录%s创建失败！" % self.image_download_path)
            tool.process_exit()

        # 下载
        page_count = 1
        image_count = 1
        new_last_blog_time = ""
        unique_list = []
        is_over = False
        while not is_over:
            log.step("开始解析第%s页图片" % page_count)

            # 获取一页图片
            photo_pagination_response = get_one_page_photo(page_count)
            if photo_pagination_response.status != net.HTTP_RETURN_CODE_SUCCEED:
                log.error("第%s页图片访问失败，原因：%s" % (page_count, robot.get_http_request_failed_reason(photo_pagination_response.status)))
                tool.process_exit()

            index_page = BeautifulSoup.BeautifulSoup(photo_pagination_response.data)
            photo_list = index_page.body.findAll("div", "photo")
            # 已经下载到最后一页
            if not photo_list:
                break

            for photo_info in photo_list:
                if isinstance(photo_info, BeautifulSoup.NavigableString):
                    continue

                # 从图片页面中解析获取推特发布时间的时间戳
                tweet_created_time = get_tweet_created_time(photo_info)
                if tweet_created_time is None:
                    log.error("第%s张图片 图片上传时间解析失败" % image_count)
                    continue

                # 检查是否已下载到前一次的图片
                if tweet_created_time <= last_blog_time:
                    is_over = True
                    break

                # 将第一张图片的上传时间做为新的存档记录
                if new_last_blog_time == "":
                    new_last_blog_time = str(tweet_created_time)

                # 从图片页面中解析获取推特发布账号
                account_id = get_tweet_account_id(photo_info)
                if account_id is None:
                    log.error("第%s张图片 解析Twitter账号失败" % image_count)
                    continue

                # 找图片
                img_tags = photo_info.findAll("img")
                for tag in img_tags:
                    tag_attr = dict(tag.attrs)
                    if robot.check_sub_key(("src", "alt"), tag_attr):
                        image_url = str(tag_attr["src"]).replace(" ", "")

                        # 新增图片导致的重复判断
                        if image_url in unique_list:
                            continue
                        else:
                            unique_list.append(image_url)

                        log.step("开始下载第%s张图片 %s" % (image_count, image_url))

                        file_type = image_url.split(".")[-1]
                        if file_type.find("/") != -1:
                            file_type = "jpg"
                        file_path = os.path.join(image_path, "%05d_%s.%s" % (image_count, account_id, file_type))
                        save_file_return = net.save_net_file(image_url, file_path)
                        if save_file_return["status"] == 1:
                            log.step("第%s张图片下载成功" % image_count)
                            image_count += 1
                        else:
                            log.error("第%s张图片（account_id：%s) %s，下载失败，原因：%s" % (image_count, account_id, image_url, robot.get_save_net_file_failed_reason(save_file_return["code"])))
                if is_over:
                    break

            if not is_over:
                page_count += 1

        log.step("下载完毕")

        # 排序复制到保存目录
        if self.is_sort:
            if not tool.make_dir(self.image_download_path, 0):
                log.error("创建目录 %s 失败" % self.image_download_path)
                tool.process_exit()

            log.step("图片开始从下载目录移动到保存目录")

            file_list = tool.get_dir_files_name(self.image_temp_path, "desc")
            for file_name in file_list:
                image_path = os.path.join(self.image_temp_path, file_name)
                file_name_list = file_name.split(".")
                file_type = file_name_list[-1]
                account_id = "_".join(".".join(file_name_list[:-1]).split("_")[1:])

                image_start_index += 1
                destination_file_name = "%05d_%s.%s" % (image_start_index, account_id, file_type)
                destination_path = os.path.join(self.image_download_path, destination_file_name)
                tool.copy_files(image_path, destination_path)

            log.step("图片从下载目录移动到保存目录成功")

            # 删除临时文件夹
            tool.remove_dir(self.image_temp_path)

        # 保存新的存档文件
        if new_last_blog_time != "":
            tool.write_file(str(image_start_index) + "\t" + new_last_blog_time, self.save_data_path, 2)

        log.step("全部下载完毕，耗时%s秒，共计图片%s张" % (self.get_run_time(), image_count - 1))


if __name__ == "__main__":
    Fkoji().main()
