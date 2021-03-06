#!/usr/bin/env python
# coding=utf-8

import re
import datetime
import urlparse
import redis
import spider
import setting
import htmlparser
import requests
from bs4 import BeautifulSoup, Comment
import allsite_clean_url

class MySpider(spider.Spider):

    def __init__(self,
                 proxy_enable=setting.PROXY_ENABLE,
                 proxy_max_num=setting.PROXY_MAX_NUM,
                 timeout=setting.HTTP_TIMEOUT,
                 cmd_args=None):
        spider.Spider.__init__(
            self, proxy_enable, proxy_max_num, timeout=timeout, cmd_args=cmd_args)
        # 网站名称
        self.siteName = "test"
        # 类别码，01新闻、02论坛、03博客、04微博 05平媒 06微信  07 视频、99搜索引擎
        self.info_flag = "01"
        # self.start_urls = 'http://www.bashan.com/' #巴山财经
        self.start_urls='http://roll.news.sina.com.cn/news/gnxw/gdxw1/index.shtml'
        # self.start_urls = 'http://www.yangtse.com/'
        # self.start_urls = 'http://www.thepaper.cn/' # 澎湃新闻
        # self.start_urls = 'http://bbs.tianya.cn/'
        # self.encoding = 'gbk' #k618 扬子晚报 地方领导留言板 北青网
        self.encoding = 'utf-8' #tianya 澎湃新闻 巴山财经
        self.site_domain = 'tianya.cn' #巴山财经
        # self.site_domain = 'yangtse.com'
        # self.site_domain = 'ynet.com' # 北青网
        # self.site_domain = 'thepaper.cn' # 澎湃新闻
        # self.site_domain = 'bbs.tianya.cn'
        # self.conn = redis.StrictRedis.from_url('redis://192.168.100.15/6')
        self.conn = redis.StrictRedis.from_url('redis://127.0.0.1/15') # 详情页专用
        self.ok_urls_zset_key = 'ok_urls_zset_%s' % self.site_domain
        self.list_urls_zset_key = 'list_urls_zset_%s' % self.site_domain
        self.error_urls_zset_key = 'error_urls_zset_%s' % self.site_domain
        self.detail_urls_zset_key = 'detail_urls_zset_%s' % self.site_domain
        self.detail_urls_rule0_zset_key = 'detail_rule0_urls_zset_%s' % self.site_domain
        self.detail_urls_rule1_zset_key = 'detail_rule1_urls_zset_%s' % self.site_domain
        self.todo_urls_limits = 10
        self.todo_flg = -1
        self.done_flg = 0
        self.detail_flg = 9
        self.max_level = 7  # 最大级别
        self.detail_level = 99
        self.dedup_key = None
        self.cleaner = allsite_clean_url.Cleaner(
            self.site_domain, redis.StrictRedis.from_url('redis://127.0.0.1/6'))


    def header_maker(self, text=''):
        if not text:
            text = {'Proxy-Connection': 'keep-alive',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Upgrade-Insecure-Requests': 1,
                    'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/48.0.2564.116 Safari/537.36',
                    'Accept-Encoding': 'gzip, deflate, sdch',
                    'Accept-Language': 'zh-CN,zh;q=0.8,en;q=0.6,zh-TW;q=0.4'
                    }
        return text

    def get_clean_soup(self, url):
        headers = self.header_maker()
        try:
            data = requests.get(url, headers=headers, timeout=5)
        except Exception, e:
            print "[error]get_clean_soup()",e
            return None
        soup = BeautifulSoup(data.content, 'lxml')
        comments = soup.findAll(text=lambda text: isinstance(text, Comment))
        [comment.extract() for comment in comments]
        [s.extract() for s in soup('script')]
        [s.extract() for s in soup('style')]
        [input.extract() for input in soup('input')]
        [input.extract() for input in soup('form')]
        [foot.extract() for foot in soup(attrs={'class': 'footer'})]
        [foot.extract() for foot in soup(attrs={'class': 'bottom'})]
        return soup

    def filter_links(self, urls):
        # print 'filter_links() start', len(urls), urls
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
        urls = filter(lambda x: not self.cleaner.in_black_list(x), urls) # bbs. mail.
        # print 'filter_links() in_black_list', len(urls)
        # 链接时间过滤
        # urls = filter(lambda x: not self.cleaner.is_old_url(x), urls)
        # 非第一页链接过滤
        urls = filter(lambda x: not self.cleaner.is_next_page(x), urls)
        # print 'filter_links() is_next_page', len(urls)
        # for url in urls:
        #     if  self.conn.zrank(self.detail_urls_zset_key, url) is not None:
        #         print 'remove:', url
        #         urls.remove(url)
        # 去重
        urls = list(set(urls))
        # print 'filter_links() set', len(urls)
        # 404
        # urls = filter(lambda x: not self.cleaner.is_not_found(x), urls)
        # print 'filter_links() end', len(urls), urls
        return urls

    def urls_join(self, org_url, links):
        # print 'urls_join() start',len(links), org_url,links
        urls = []
        for link in links:
            scheme, netloc, path, params, query, fragment = urlparse.urlparse(link.strip())
            if scheme:
                url = urlparse.urlunparse((scheme, netloc, path, params, query, ''))
            else:
                link = urlparse.urlunparse(('', '', path, params, query, ''))
                # url = urlparse.urljoin(org_url, urllib.quote(link))
                url = urlparse.urljoin(org_url, link)
            urls.append(url)

        # print 'urls_join() end', len(links), urls
        return urls

    def is_current_page(self, soup, org_url):
        for tag in soup.find_all(text=re.compile(u"正文")):
            parent = tag.find_parent(recursive=False)
            if len(parent.find_all('a')) > 0:
                return True

        return False

    def is_list_by_link_density(self, soup):
        all_text = []
        for str in soup.body.stripped_strings:
            all_text.append(str)
        all_str = ''.join(all_text)
        all_str = re.compile(r"\s+", re.I | re.M | re.S).sub('', all_str)
        # 去掉冗余：时间标示
        all_str = re.compile(r"\d{4}[\-|\/]\d{2}[\-|\/]\d{4}\:\d{2}", re.I | re.M | re.S).sub('', all_str)
        all_str = re.compile(r"\d{4}[\-|\/]\d{2}[\-|\/]\d{2}", re.I | re.M | re.S).sub('', all_str)
        # print 'all_str:', len(all_str), all_str

        links_text = []
        for tag in soup.findAll('a'):
            for str in tag.stripped_strings: links_text.append(str)
        link_str = ''.join(links_text)
        link_str = re.compile(r"\s+", re.I | re.M | re.S).sub('', link_str)
        # print 'link_str:', len(link_str), link_str

        rate = float(len(link_str)) / len(all_str)
        # print 'is_list_by_link_density() rate:', rate
        return rate > 0.6

    def is_list_by_rule(self, soup, url):
        # print 'is_list_by_rule start'
        path = urlparse.urlparse(url).path
        if len(path) == 0:
            return True
        else:
            # 最优先确定规则
            if path == '/':
                return True
            if path[-1] == '/':
                return True
            if path.lower().find('index') > 0 or path.lower().find('list') > 0:
                return True
            if path.lower().find('post') > 0 or path.lower().find('content') > 0 or path.lower().find('detail') > 0:
                return False
            if path[1:].isalpha():
                return True
            if self.conn.zrank(self.list_urls_zset_key, url):
                return True
            # 判断面包屑中有无的‘正文’
            if self.is_current_page(soup, url) == True:
                return False
            # 使用链接密度
            return self.is_list_by_link_density(soup)
        # print 'is_list_by_rule start',url,ret

    def get_todo_urls(self):
        urls = []
        try:
            urls = self.conn.zrangebyscore(self.list_urls_zset_key, self.done_flg, self.done_flg)
            if len(urls) > self.todo_urls_limits:
                urls = urls[0:self.todo_urls_limits]
            for url in urls:
                self.conn.zadd(self.list_urls_zset_key, self.detail_flg, url)
        except Exception, e:
            print "[ERROR] get_todo_urls(): %s" % e
        return urls

    def get_page_valid_urls_short(self, soup, org_url):
        # print 'get_page_valid_urls_short() start',org_url
        all_links = []
        remove_links = []
        try:
            for tag in soup.find_all("a", text=re.compile(u"[\w\W]{,10}")):
                if tag.has_attr('href'):
                    all_links.append(tag['href'])

            for tag in soup.find_all("a", href=re.compile(r"(javascript.*?|#.*?)", re.I)):
                if tag.has_attr('href'):
                    remove_links.append(tag['href'])

            tag = soup.find("a", text=re.compile(u"下一页"))
            if tag:
                if tag.has_attr('href'):
                    remove_links.append(tag['href'])

                for t in tag.find_previous_siblings('a', recursive=False):
                    if t.has_attr('href'):
                        remove_links.append(t['href'])

                for t in tag.find_next_siblings('a', recursive=False):
                    if t.has_attr('href'):
                        remove_links.append(t['href'])

        except Exception, e:
            print '[ERROR] get_page_valid_urls_short()',e

        removed = list(set(all_links) - set(remove_links))

        links = self.urls_join(org_url, removed)
        # print len(all_links), all_links
        # print len(remove_links), remove_links
        # print len(removed), removed
        # print len(urls), urls
        links = self.filter_links(links)
        for link in links:
            soup = self.get_clean_soup(link)
            if soup and self.is_list_by_rule(soup, link) is False:
                if self.conn.zrank(self.detail_urls_zset_key, link) is None:
                    self.conn.zadd(self.detail_urls_zset_key, self.done_flg, link)

        # print 'get_page_valid_urls_short() end',len(links), links
        return links

    def get_page_valid_urls_long(self, soup, org_url):
        # print 'get_page_valid_urls_long() start', org_url
        urls = []
        all_links = []
        remove_links = []
        try:
            for tag in soup.find_all("a", text=re.compile(u"[\w\W]{10,}")):
                if tag.has_attr('href'):
                    all_links.append(tag['href'])

            for tag in soup.find_all("a", href=re.compile(r"(javascript.*?|#.*?)", re.I)):
                if tag.has_attr('href'):
                    remove_links.append(tag['href'])

        except Exception, e:
            print '[ERROR] get_page_valid_urls_long()', e

        removed = list(set(all_links) - set(remove_links))

        links = self.urls_join(org_url, removed)
        # print 'get_page_valid_urls_long() urls_join', urls
        links = self.filter_links(links)
        # print 'get_page_valid_urls_long() filter_links',urls
        for link in links:
            if self.conn.zrank(self.detail_urls_zset_key, link) is None:
                self.conn.zadd(self.detail_urls_zset_key, self.done_flg, link)
        # print 'get_page_valid_urls_long() end', len(links), links
        return links

    def get_start_urls(self, data=None):
        return [self.start_urls]

    def parse(self, response):
        urls = self.get_todo_urls()
        return urls, None, None

    def parse_detail_page(self, response=None, url=None):
        # print 'parse_detail_page() start',org_url
        if response is None: return []

        if url is None:
            org_url = response.request.url
        else:
            org_url = response.url

        soup = self.get_clean_soup(org_url)
        if soup:
            self.get_page_valid_urls_long(soup, org_url)
            self.get_page_valid_urls_short(soup, org_url)
        # print 'parse_detail_page() end'
        return []

# ---------- test run function-----------------------------
def make_test_list(urls):
    mySpider = MySpider()
    for url in urls:
        mySpider.conn.zadd(mySpider.list_urls_zset_key, mySpider.done_flg, url)

def test(unit_test):
    if unit_test is False: # spider simulation
        print '[spider simulation] now starting ..........'
        for cnt in range(10):
            print '[loop]',cnt,'[time]',datetime.datetime.utcnow()
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
                                print '[ERROR] main() Exception: %s' % e
                                list_urls, callback, next_page_url = [], None, None

                            __detail_page_urls(list_urls, callback)

                            if next_page_url is not None:
                                print 'next_page_url'
                                __detail_page_urls([next_page_url], func)

            # --equal to run.py list_page_thread() -------------------------
            mySpider = MySpider()
            mySpider.proxy_enable = False
            mySpider.init_dedup()
            mySpider.init_downloader()
            start_urls = mySpider.get_start_urls()  # get_start_urls()
            __detail_page_urls(start_urls, mySpider.parse)  # parse()

            # --equal to run.py detail_page_thread() -------------------------
            for url in detail_job_list:
                resp = mySpider.download(url)
                ret = mySpider.parse_detail_page(resp, url)  # parse_detail_page()
                for item in ret:
                    for k, v in item.iteritems():
                        print k, v
    else: # ---------- unit test -----------------------------
        print '[unit test] now starting ..........'
        # url = 'http://baike.k618.cn/aaa/thread-3327665-1-1.html'
        url = 'http://p.bashan.com/xinggan/1118.html' #详情页 图片多 bug
        make_test_list(url)
        mySpider = MySpider()
        soup = mySpider.get_clean_soup(url)
        # print soup
        if soup is None:
            print '[ERROR] url is invalid.'
            return
        #----------------------------------------------------------
        # print mySpider.is_list_by_rule(url)
        #----------------------------------------------------------
        # rule0 = mySpider.convert_path_to_rule0(url)
        # print url, '->', rule0
        # rule1 = mySpider.convert_path_to_rule1(rule0)
        # print rule0, '->', rule1
        print mySpider.is_list_by_link_density(soup)

if __name__ == '__main__':
    urls = ['http://blog.tianya.cn/']
    make_test_list(urls)
    test(unit_test = False)
    # test(unit_test = True)
    # import cProfile
    # cProfile.run("test(unit_test = False)")
