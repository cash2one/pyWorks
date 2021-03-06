#!/usr/bin/python
# coding=utf-8

import re
import os
import datetime
import urlparse
import redis
import spider
import setting
import log
import ConfigParser
from bs4 import BeautifulSoup, Comment
import requests
import allsite_clean_url
import traceback

####################################################################
# MY_OS = os.getenv('SPIDER_OS')
# if MY_OS is None:
#     # log.logger.error('[ERROR] must be set a SPIDER_OS env.')
#     print '[ERROR] must be set a MY_OS.'
#     exit(-1)
# else:
#     # log.logger.info('[info]--- The OS is: %s ----' % MY_OS)
#     print '[info]--- allsite_spider_list The OS is: %s ----' % MY_OS
#     if MY_OS == 'linux':
#         INIT_CONFIG = '/work/spider/allsite_spider.ini'
#     elif MY_OS == 'mac':
#         INIT_CONFIG = '/Users/song/workspace/pyWorks/spider/allsite_spider.ini'
#     else:  # windows
#         INIT_CONFIG = './allsite_spider.ini'
# ####################################################################
# config = ConfigParser.ConfigParser()
# if len(config.read(INIT_CONFIG)) == 0:
#     # log.logger.error('[ERROR]cannot read the config file. %s' % INIT_CONFIG)
#     print '[ERROR]cannot read the config file.', INIT_CONFIG
#     exit(-1)
# else:
#     # log.logger.info('[INFO] read the config file.%s' % INIT_CONFIG)
#     print '[INFO] read the config file.', INIT_CONFIG

# redis
# REDIS_SERVER = config.get('redis', 'redis_server')
# DEDUP_SERVER = config.get('redis', 'dedup_server')

# spider-modify-start
USER_ID = '''admin'''

REDIS_SERVER = '''redis://127.0.0.1/14'''
DEDUP_SERVER = '''redis://127.0.0.1/14'''

MODE = '''exact'''

START_URLS = '''http://bbs.tianya.cn'''
SITE_DOMAIN = '''bbs.tianya.cn'''
BLACK_DOMAIN_LIST = ''''''

LIST_RULE_LIST = '''/^uid/@/^username/@/^space/@/^search/@/^blog/@/^group/@list@index@forum@fid@'''
DETAIL_RULE_LIST = '''post@thread@detail@content@'''


# spider-modify-end

# MODE = config.get('spider', 'mode')
# START_URLS = config.get('spider', 'start_urls')
# SITE_DOMAIN = config.get('spider', 'site_domain')
# BLACK_DOMAIN_LIST = config.get('spider', 'black_domain_list')
# DETAIL_RULE_LIST = config.get('spider', 'detail_rule_list')
# LIST_RULE_LIST = config.get('spider', 'list_rule_list')


############################################################################
class MySpider(spider.Spider):
    def __init__(self,
                 proxy_enable=setting.PROXY_ENABLE,
                 proxy_max_num=setting.PROXY_MAX_NUM,
                 timeout=setting.HTTP_TIMEOUT,
                 cmd_args=None):
        spider.Spider.__init__(
            self, proxy_enable, proxy_max_num, timeout=timeout, cmd_args=cmd_args)
        # 网站名称
        self.siteName = "all"
        # 类别码，01新闻、02论坛、03博客、04微博 05平媒 06微信  07 视频、99搜索引擎
        self.info_flag = "01"
        self.start_urls = START_URLS
        self.site_domain = SITE_DOMAIN
        self.black_domain_list = BLACK_DOMAIN_LIST
        self.encoding = 'utf-8'
        self.conn = redis.StrictRedis.from_url(REDIS_SERVER)
        self.task_manager_key = 'task_manager'  # 任务管理
        self.list_urls_zset_key = 'list_urls_zset_%s' % self.site_domain  # 计算结果(列表)
        self.detail_urls_set_key = 'detail_urls_set_%s' % self.site_domain  # 计算结果(详情)
        self.unkown_urls_set_key = 'unkown_urls_set_%s' % self.site_domain  # 计算结果(未知)
        self.manual_w_list_rule_zset_key = 'manual_w_list_rule_zset_%s' % self.site_domain  # 手工配置规则(白)
        self.manual_b_list_rule_zset_key = 'manual_b_list_rule_zset_%s' % self.site_domain  # 手工配置规则（黑）
        self.manual_w_detail_rule_zset_key = 'manual_w_detail_rule_zset_%s' % self.site_domain  # 手工配置规则(白)
        self.manual_b_detail_rule_zset_key = 'manual_b_detail_rule_zset_%s' % self.site_domain  # 手工配置规则（黑）
        self.detail_rules = []
        self.list_rules = []
        self.todo_urls_limits = 10
        self.todo_flg = -1
        self.done_flg = 0
        self.max_level = 7  # 最大级别
        self.detail_level = 99
        self.dedup_key = 'dedup'
        self.cleaner = allsite_clean_url.Cleaner(
            site_domain=self.site_domain,
            black_domain_str=self.black_domain_list,
            conn=redis.StrictRedis.from_url(REDIS_SERVER))

    def filter_links(self, urls):
        # print '[INFO]filter_links() start', len(urls), urls
        try:
            # 下载页
            urls = filter(lambda x: self.cleaner.is_suffixes_ok(x), urls)
            # print 'filter_links() is_download', len(urls)
            # 错误url识别
            urls = filter(lambda x: not self.cleaner.is_error_url(x), urls)
            # print 'filter_links() is_error_url', len(urls)
            # 清洗无效参数#?
            urls = self.cleaner.url_clean(urls)
            # 跨域检查
            urls = filter(lambda x: self.cleaner.check_cross_domain(x), urls)
            # print 'filter_links() check_cross_domain', len(urls)
            # 黑名单过滤
            urls = filter(lambda x: not self.cleaner.in_black_list(x), urls)  # bbs. mail.
            # print 'filter_links() in_black_list', len(urls)
            # 链接时间过滤
            # urls = filter(lambda x: not self.cleaner.is_old_url(x), urls)
            # 非第一页链接过滤
            urls = filter(lambda x: not self.cleaner.is_next_page(x), urls)
            # print 'filter_links() is_next_page', len(urls)
            # 去重
            urls = list(set(urls))
            # print 'filter_links() set', len(urls)
            # 404
            # urls = filter(lambda x: not self.cleaner.is_not_found(x), urls)
            # print '[INFO]filter_links() end', len(urls), urls
        except Exception, e:
            log.logger.error('[ERROR]filter_links() %s' % e)
            # print '[ERROR]filter_links()', e
        return urls

    def path_is_list(self, url):
        scheme, netloc, path, params, query, fragment = urlparse.urlparse(url)
        new_url = urlparse.urlunparse(('', '', path, params, query, ''))
        score = float(0)
        # 页面手工配置规则
        for rule in self.list_rules:
            if rule.find('/^') >= 0:  # 黑
                if re.search(rule[2:-1], url):  # 去掉 /^xxxxxx/ 中的 '/^','/'
                    self.conn.zincrby(self.manual_b_list_rule_zset_key, value=rule, amount=1)
                    # print '[list-black]', rule, '<-', url
                    return 'black'  # 符合详情页规则（黑）
            else:  # 白
                if re.search(rule, url):
                    self.conn.zincrby(self.manual_w_list_rule_zset_key, value=rule, amount=1)
                    s = self.conn.zscore(self.manual_w_list_rule_zset_key, value=rule)
                    score += (s - int(s))
                    # print '[list-white]', (s - int(s)), rule, '<-', url

        for rule in self.detail_rules:
            if rule.find('/^') >= 0:  # 黑
                if re.search(rule[2:-1], url):  # 去掉 /^xxxxxx/ 中的 '/^','/'
                    self.conn.zincrby(self.manual_b_detail_rule_zset_key, value=rule, amount=1)
                    # print '[detail-black]', rule, '<-', url
                    return 'black'  # 符合详情页规则（黑）
            else:  # 白
                if re.search(rule, url):
                    self.conn.zincrby(self.manual_w_detail_rule_zset_key, value=rule, amount=1)
                    s = self.conn.zscore(self.manual_w_detail_rule_zset_key, value=rule)
                    score -= (s - int(s))
                    # print '[detail-white]', -(s - int(s)), rule, '<-', url

        if score <= -0.25:
            # log.logger.info('[detail],%s' % url)
            print '[detail]', score, url
            return 'detail'
        elif score >= 0.25:
            # log.logger.info('[list],%s' % url)
            print '[list]', score, url
            return 'list'
        else:
            # log.logger.info('[unkown],%s' % url)
            print '[unkown]', score, url
            return 'unkown'

    def get_todo_urls(self):
        urls = []
        try:
            urls = self.conn.zrangebyscore(self.list_urls_zset_key, self.todo_flg, self.todo_flg)
            if len(urls) > self.todo_urls_limits:
                urls = urls[0:self.todo_urls_limits]
            for url in urls:
                self.conn.zadd(self.list_urls_zset_key, self.done_flg, url)
                # print 'get_todo_urls()', urls
        except Exception, e:
            # log.logger.error('[ERROR]get_todo_urls() %s' % e)
            print "[ERROR] get_todo_urls(): %s" % e
        return urls

    # def header_maker(self, text=''):
    #     if not text:
    #         text = {'Proxy-Connection': 'keep-alive',
    #                 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    #                 'Upgrade-Insecure-Requests': 1,
    #                 'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/48.0.2564.116 Safari/537.36',
    #                 'Accept-Encoding': 'gzip, deflate, sdch',
    #                 'Accept-Language': 'zh-CN,zh;q=0.8,en;q=0.6,zh-TW;q=0.4'
    #                 }
    #     return text

    def get_clean_soup(self, response):
        # headers = self.header_maker()
        # try:
        #     data = requests.get(url, headers=headers, timeout=5)
        # except Exception, e:
        #     print "[ERROR]get_clean_soup()", e
        #     return None
        # soup = BeautifulSoup(data.content, 'lxml')
        soup = BeautifulSoup(response.content, 'lxml')
        # print 'before',soup.prettify()
        comments = soup.findAll(text=lambda text: isinstance(text, Comment))
        [comment.extract() for comment in comments]
        [s.extract() for s in soup('script')]
        [s.extract() for s in soup('style')]
        [input.extract() for input in soup('input')]
        [input.extract() for input in soup('form')]
        [foot.extract() for foot in soup(attrs={'class': 'footer'})]
        [foot.extract() for foot in soup(attrs={'class': 'bottom'})]
        # print 'after',soup.prettify()
        return soup

    def urls_join(self, org_url, links):
        # print '[INFO]urls_join() start',org_url,links
        urls = []
        for link in links:
            scheme, netloc, path, params, query, fragment = urlparse.urlparse(link.strip())
            if path == '': path = '/'
            if scheme:
                url = urlparse.urlunparse((scheme, netloc, path, params, query, ''))
            else:
                link = urlparse.urlunparse(('', '', path, params, query, ''))
                # url = urlparse.urljoin(org_url, urllib.quote(link))
                # print '[INFO]urljoin()', org_url, link
                url = urlparse.urljoin(org_url, link)

            urls.append(url)

        # print '[INFO]urls_join() end', urls
        return urls

    def urls_join_plus(self, org_url, links):
        # print '[INFO]urls_join_plus() start', org_url, links
        urls = []
        o_scheme, o_netloc, o_path, o_params, o_query, o_fragment = urlparse.urlparse(org_url.strip())
        for link in links:
            if link.find('http') >= 0:
                urls.append(link)
            else:
                l = o_scheme + '://' + o_netloc + '/' + link
                urls.append(l)
        # print '[INFO]urls_join_plus() end', urls
        return urls

    def get_page_valid_urls(self, soup, org_url):
        # print '[INFO]get_page_valid_urls() start'
        all_links = []
        remove_links = []
        try:
            for tag in soup.find_all("a"):
                if tag.has_attr('href'):
                    all_links.append(tag['href'])

            for tag in soup.find_all("a", href=re.compile(r"(javascript.*?|#.*?)", re.I)):
                if tag.has_attr('href'):
                    remove_links.append(tag['href'])

                    # tag = soup.find("a", text=re.compile(u"下一页")) # 下一页 下页
                    # if tag:
                    #     if tag.has_attr('href'):
                    #         remove_links.append(tag['href'])
                    #
                    #     for t in tag.find_previous_siblings('a', recursive=False):
                    #         if t.has_attr('href'):
                    #             remove_links.append(t['href'])
                    #
                    #     for t in tag.find_next_siblings('a', recursive=False):
                    #         if t.has_attr('href'):
                    #             remove_links.append(t['href'])

        except Exception, e:
            # log.logger.error('[ERROR]get_page_valid_urls() %s' % e)
            print '[ERROR]get_page_valid_urls()', e

        removed = list(set(all_links) - set(remove_links))

        urls = self.urls_join(org_url, removed)
        # print len(all_links), all_links
        # print len(remove_links), remove_links
        # print len(removed), removed
        # print len(urls), urls
        urls = self.filter_links(urls)
        # print '[INFO]get_page_valid_urls() end'
        return urls

    def is_task_run(self):
        k = USER_ID + '@' + self.site_domain + '@' + 'list'
        # task_manager 存在，并且task_manager中相应任务的状态为start。
        try:
            if self.conn.exists(self.task_manager_key):
                if self.conn.hexists(self.task_manager_key, k):
                    v = self.conn.hget(self.task_manager_key, k)
                    status = eval(v).get('status')
                    if status == 'start':
                        return True
        except Exception, e:
            print '[ERROR]is_killed()', e
            print traceback.format_exc()

        return False

    def get_start_urls(self, data=None):
        if self.is_task_run() == False:
            return []

        self.detail_rules = [x.strip() for x in DETAIL_RULE_LIST.split('@') if x != '']
        # print '[INFO]get_start_urls() detail ini:', DETAIL_RULE_LIST, '->', self.detail_rules
        self.list_rules = [x.strip() for x in LIST_RULE_LIST.split('@') if x != '']
        # print '[INFO]get_start_urls() list ini:', LIST_RULE_LIST, '->', self.list_rules
        if self.conn.zrank(self.list_urls_zset_key, self.start_urls) is None:
            self.conn.zadd(self.list_urls_zset_key, self.todo_flg, self.start_urls)
        return [self.start_urls]

    def parse(self, response):
        urls = self.get_todo_urls()
        return urls, None, None

    def parse_detail_page(self, response=None, url=None):
        # print '[INFO]parse_detail_page() start'
        result = []
        if response is None: return result

        if url is None:
            org_url = response.request.url
        else:
            org_url = response.url

        try:
            soup = self.get_clean_soup(response)
            if soup is None: return []
            links = self.get_page_valid_urls(soup, org_url)
            for link in links:
                ret = self.path_is_list(link)
                if ret == 'black':
                    continue
                elif ret == 'list':
                    if self.conn.zrank(self.list_urls_zset_key, link) is None:
                        # self.conn.zadd(self.list_urls_zset_key, self.todo_flg, urllib.unquote(link))
                        self.conn.zadd(self.list_urls_zset_key, self.todo_flg, link)
                elif ret == 'detail':
                    # self.conn.sadd(self.detail_urls_set_key, urllib.unquote(link))
                    self.conn.sadd(self.detail_urls_set_key, link)
                else:  # unkown
                    self.conn.sadd(self.unkown_urls_set_key, link)
                    if MODE == 'all':
                        if self.conn.zrank(self.list_urls_zset_key, link) is None:
                            # self.conn.zadd(self.list_urls_zset_key, self.todo_flg, urllib.unquote(link))
                            self.conn.zadd(self.list_urls_zset_key, self.todo_flg, link)

        except Exception, e:
            log.logger.error('[ERROR]parse_detail_page() %s [url] %s' % (e, org_url))
            # print "[ERROR] parse_detail_page(): %s [url] %s" % (e, org_url)
        return result


# ---------- main function-----------------------------
def main(unit_test):
    if unit_test is False:  # spider simulation
        log.logger.info('[spider simulation] now starting')
        # print '[spider simulation] now starting ..........'
        for cnt in range(10000):
            log.logger.info('[loop] %d' % cnt)
            # print '[loop]', cnt, '[time]', datetime.datetime.utcnow()
            detail_job_list = []  # equal to run.py detail_job_queue

            # ---equal to run.py get_detail_page_urls(spider, urls, func, detail_jo
            def __detail_page_urls(urls, func):
                next_page_url = None
                if func is not None:
                    if urls:
                        for url in urls:
                            try:
                                response = mySpider.download(url)
                                list_urls, callback, next_page_url = func(response)  # parse()
                                for url in list_urls:
                                    detail_job_list.append(url)
                            except Exception, e:
                                log.logger.error('[ERROR]main() %s' % (e))
                                # print '[ERROR] main() Exception: %s' % e
                                list_urls, callback, next_page_url = [], None, None

                            __detail_page_urls(list_urls, callback)

                            if next_page_url is not None:
                                # print 'next_page_url'
                                __detail_page_urls([next_page_url], func)

            # --equal to run.py list_page_thread() -------------------------
            mySpider = MySpider()
            mySpider.proxy_enable = False
            mySpider.init_dedup()
            mySpider.init_downloader()
            start_urls = mySpider.get_start_urls()  # get_start_urls()
            # print '[test]start_urls:', start_urls
            __detail_page_urls(start_urls, mySpider.parse)  # parse()

            # --equal to run.py detail_page_thread() -------------------------
            ret = []
            for url in detail_job_list:
                resp = mySpider.download(url)
                ret = mySpider.parse_detail_page(resp, url)  # parse_detail_page()
                # for item in ret:
                #     for k, v in item.iteritems():
                # print k, v
    else:  # ---------- unit test -----------------------------
        # print '[unit test] now starting ..........'
        url = 'http://bbs.tianya.cn/hotArticle/index/post-41-1236689-1.shtml'
        # url = 'http://cpt.xtu.edu.cn/a/keyanchengguo/keyanxiangmu/2013/0414/109.html'
        # print 'url:', url
        mySpider = MySpider()
        # 预置数据
        # 预置匹配规则
        mySpider.get_start_urls()
        # mySpider.init_downloader()
        # resp = mySpider.download(url)
        # soup = mySpider.get_clean_soup(resp)
        # ----------------------------------------------------------
        # print mySpider.path_is_list(url)
        # ----------------------------------------------------------
        # rule0 = mySpider.convert_path_to_rule0(url)
        # print url, '->', rule0
        # rule1 = mySpider.convert_path_to_rule1(rule0)
        # print rule0, '->', rule1


if __name__ == '__main__':
    main(unit_test=False)
    # main(unit_test=True)
    # import cProfile
    # cProfile.run("main(unit_test = False)")
