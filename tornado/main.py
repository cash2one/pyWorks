#!/usr/bin python
# coding=utf-8

import os.path
import json
import datetime
import re
import signal
import requests
import redis
import pymongo
import time
from math import *

import tornado.autoreload
from pprint import pprint
import tornado.locale
import tornado.auth
import tornado.escape
import tornado.httpserver
import tornado.ioloop
import tornado.options
from tornado.log import LogFormatter
import tornado.web
from tornado.escape import json_encode
from tornado.options import define, options

# import ConfigParser
#
# config = ConfigParser.ConfigParser()
# if len(config.read('./user_conf.ini')) == 0:
#     print '[error] cannot read the config file.'
#     exit(-1)
# else:
#     print '[info] read the config file.'
#
# USER_AREA = config.get('user', 'user_area')
# print '[info] user area is :', USER_AREA

REDIS_SERVER = 'redis://127.0.0.1/10'
MONGODB_SERVER = '127.0.0.1'  # '192.168.187.4'
MONGODB_PORT = 27017  # '37017'

# local_flg 0: 附近的人  2：朋友圈
FRIENDS_FLG = 2
AROUND_FLG = 0
PAGE_NUM = 10

define("port", default=5000, help="run on the given port", type=int)

amap_key = '0c7fb71b2e13546416337666cd406db3'  # 高德地图JavaScriptAPI key 220.249.18.226
# baidu_map_key = 'e9ospC88hj5iHoI9xUabaHFYAEiFXlRa'
baidu_map_key = '4119853f8e9c07a0eeaf89352b2c795d'


# logger = LogFormatter()

class Util(object):
    @staticmethod
    def calc_distance((Lng_A, Lat_A), (Lng_B, Lat_B)):
        '''
            Lng_A = 118.796877, Lat_A = 32.060255  # 南京
            Lng_B = 116.407395, Lat_B = 39.904211  # 北京
            Lat_A 纬度A, Lng_A 经度A
            Lat_B 纬度B, Lng_B 经度B
            distance 距离(km)
        '''
        print '[info] calc_distance() ', (Lng_A, Lat_A), (Lng_B, Lat_B)
        ra = 6378.140  # 赤道半径 (km)
        rb = 6356.755  # 极半径 (km)
        flatten = (ra - rb) / ra  # 地球扁率
        rad_lat_A = radians(float(Lat_A))
        rad_lng_A = radians(float(Lng_A))
        rad_lat_B = radians(float(Lat_B))
        rad_lng_B = radians(float(Lng_B))
        pA = atan(rb / ra * tan(rad_lat_A))
        pB = atan(rb / ra * tan(rad_lat_B))
        xx = acos(sin(pA) * sin(pB) + cos(pA) * cos(pB) * cos(rad_lng_A - rad_lng_B))
        c1 = (sin(xx) - xx) * (sin(pA) + sin(pB)) ** 2 / cos(xx / 2) ** 2
        c2 = (sin(xx) + xx) * (sin(pA) - sin(pB)) ** 2 / sin(xx / 2) ** 2
        dr = flatten / 8 * (c1 - c2)
        distance = ra * (xx + dr)
        return distance
        # print('(Lat_A, Lng_A)=({0:10.3f},{1:10.3f})'.format(Lat_A, Lng_A))
        # print('(Lat_B, Lng_B)=({0:10.3f},{1:10.3f})'.format(Lat_B, Lng_B))
        # print('Distance={0:10.3f} km'.format(distance))

    def convert_str_xy_to_x_y(self, str_x_y):
        '''
        Args:
            str_x_y: '116.322987_39.983424','116.322987,39.983424'
        Returns:
            str type (x,y)
        '''
        (x, y) = (None, None)
        if str_x_y != u'None' and len(str_x_y) > 0:
            sp = '_' if '_' in str_x_y else ','
            x = str_x_y.split(sp)[0]
            y = str_x_y.split(sp)[1]
            # logger.format('convert_str_xy_to_x_y() %s %s %s' % (str_x_y, x, y))
        return (x, y)

    def convert_xy_to_address(self, str_x_y):
        '''
        Args:
            str_x_y: '39.983424_116.322987'
        Returns:
            '北京市海淀区中关村大街27号1101-08室'
        '''
        address = u'位置信息不明'
        (x, y) = self.convert_str_xy_to_x_y(str_x_y)
        if x:
            url = 'http://api.map.baidu.com/geocoder/v2/?callback=renderReverse&' \
                  'location=%s,%s&output=json&pois=0&ak=%s' % (x, y, baidu_map_key)

            # logger.format('[info] convert_xy_to_address() %s' % url)
            response = requests.get(url)
            content = response.content[len('renderReverse&&renderReverse('):-1]
            j = json.loads(content)
            address = j['result']['sematic_description']

        return address

    def convert_xy_to_addressComponent(self, str_x_y):
        '''
        Args:
            str_x_y: '39.983424_116.322987'
        Returns:
                "addressComponent": {
                                      "country": "中国",
                                      "country_code": 0,
                                      "province": "北京市",
                                      "city": "北京市",
                                      "district": "海淀区",
                                      "adcode": "110108",
                                      "street": "中关村大街",
                                      "street_number": "27号1101-08室",
                                      "direction": "附近",
                                      "distance": "7"
                                    },
        '''
        addressComponent = {"country": "",
                            "country_code": 0,
                            "province": "",
                            "city": "",
                            "district": "",
                            "adcode": "",
                            "street": "",
                            "street_number": "",
                            "direction": "",
                            "distance": ""
                            }
        (x, y) = self.convert_str_xy_to_x_y(str_x_y)
        if x:
            url = 'http://api.map.baidu.com/geocoder/v2/?callback=renderReverse&' \
                  'location=%s,%s&output=json&pois=0&ak=%s' % (x, y, baidu_map_key)

            # logger.format('[info] convert_xy_to_address() %s' % url)
            response = requests.get(url)
            content = response.content[len('renderReverse&&renderReverse('):-1]
            j = json.loads(content)
            addressComponent = j['result']['addressComponent']

        return addressComponent

    @staticmethod
    def time_min(ago_time_str):
        '''
        Args:
            ago_time_str: 例：'1 hour' or '2 minutes'
        Returns:
            计算XX时间之前的结果
        '''
        ret_time = datetime.datetime.now()
        if ago_time_str is None:
            return ret_time

        num_str = re.match(re.compile(r"(\d+)\s[a-zA-Z]+"), ago_time_str)
        if num_str:
            num = int(num_str.group(1))
            if 'second' in ago_time_str:
                ret_time = (ret_time - datetime.timedelta(seconds=num))
            if 'minute' in ago_time_str:
                ret_time = (ret_time - datetime.timedelta(minutes=num))
            if 'hour' in ago_time_str:
                ret_time = (ret_time - datetime.timedelta(hours=num))
            if 'day' in ago_time_str:
                ret_time = (ret_time - datetime.timedelta(days=num))

        # print ret_time.strftime("%Y-%m-%d %H:%M:%S")
        return ret_time

    @staticmethod
    def convert_ago_time_to_days(timestamp):
        now = datetime.datetime.now()
        t = datetime.datetime.utcfromtimestamp(timestamp)
        if now > t:
            num_str = re.match(re.compile(r"(\d+)\s[a-z]+"), str(now - t)).group(1)
            return num_str + u'天前'
        else:
            return u'未知时间'

    def get_loginUser(self):
        return 'admin'


class SessionManager(object):
    def __init__(self):
        self.conn = redis.StrictRedis.from_url(REDIS_SERVER)
        self.snsInfo_hset_key = '_session_hset'
        self.pages_hset_key = '_pages_hset'
        self.current = 'current'  # index

    def set_around_search_result(self, userId, snsId_list):
        if self.conn.exists(userId + self.snsInfo_hset_key):
            self.conn.delete(userId + self.snsInfo_hset_key)
        i = 1
        for sns_info in snsId_list:
            self.conn.hset(userId + self.snsInfo_hset_key, i, sns_info['snsId'])
            i = i + 1

        self.conn.hset(userId + self.pages_hset_key, self.current, 1)

    def get_around_search_result(self, userId, action):
        snsId_list = []
        current = self.conn.hget(userId + self.pages_hset_key, self.current)
        current = int(current)
        total = self.conn.hlen(userId + self.snsInfo_hset_key)
        print 'action:', action, 'current:', current, 'total:', total
        if total <= PAGE_NUM:  # 不足1页
            start = 1
            end = total
        else:
            if action == 'next':
                if current + PAGE_NUM >= total:  # 已经是末页
                    start = current
                    end = total
                else:
                    start = current + PAGE_NUM
                    end = start + PAGE_NUM - 1
                    if start <= total and total <= end:
                        end = total

            else:  # action：pre
                if current == 1:  # 已经是首页
                    start = 1
                    end = PAGE_NUM
                else:
                    start = current - PAGE_NUM
                    end = start + PAGE_NUM - 1

        self.conn.hset(userId + self.pages_hset_key, self.current, start)

        print 'start:', start, 'end:', end
        for i in range(start, end):
            snsId_list.append(self.conn.hget(userId + self.snsInfo_hset_key, i))

        return snsId_list


class DBDriver(object):
    def __init__(self):
        self.util = Util()
        self.client = pymongo.MongoClient(MONGODB_SERVER, MONGODB_PORT)
        self.db = self.client.wx_sns_data
        self.sns_info = self.db.sns_info
        self.lbs_info = self.db.lbs_info
        self.users = self.db.users
        self.db_patch_location = self.db.db_patch_location  # drivers
        self.sns_info_patch = self.db.sns_info_patch

    def patch_address(self):
        l = self.sns_info.find({"localFlag": AROUND_FLG})
        cnt = 0
        for i in l:
            print cnt
            if i['rawXML']['TimelineObject'].has_key('location'):
                x = i['rawXML']['TimelineObject']['location']['@latitude']
                y = i['rawXML']['TimelineObject']['location']['@longitude']
                if x != '0.0':
                    str_x_y = x + '_' + y
                    addressComponent = self.util.convert_xy_to_addressComponent(str_x_y)

                    snsId = i['snsId']
                    country = addressComponent['country']
                    province = addressComponent['province']
                    city = addressComponent['city']
                    district = addressComponent['district']
                    adcode = addressComponent['adcode']
                    street = addressComponent['street']

                    self.sns_info_patch.insert({"snsId": snsId,
                                                "country": country,
                                                "province": province,
                                                "city": city,
                                                "district": district,
                                                "adcode": adcode,
                                                "street": street,
                                                "latitude": x,
                                                "longitude": y})
            cnt = cnt + 1

    def get_friends(self):
        authors = []
        l = self.sns_info.find({"localFlag": FRIENDS_FLG}).sort("authorName")
        for sns_info in l:
            author = sns_info["authorName"]
            authors.append(author)

        return list(set(authors))

    def get_around(self):
        authors = []
        l = self.lbs_info.find({"localFlag": AROUND_FLG}).sort("authorName")
        for sns_info in l:
            author = sns_info["authorName"]
            authors.append(author)

        return list(set(authors))

    def get_address_form_patch(self, (x, y)):
        poi_address = u'地点未知'
        l = self.sns_info_patch.find_one({"longitude": x,
                                          "latitude": y})
        if l and l['street']:
            poi_address = l['city'] + u' · ' + l['district'] + l['street']

        return poi_address

    def patch_agoDays_address(self, sns_info):
        ctime = sns_info["timestamp"]
        ago_days = Util.convert_ago_time_to_days(ctime)

        poi_address = u'未知地点'
        if sns_info['rawXML']['TimelineObject'].has_key('location'):
            sns_info_x = sns_info['rawXML']['TimelineObject']['location']['@longitude']
            sns_info_y = sns_info['rawXML']['TimelineObject']['location']['@latitude']
            if sns_info_x != '0.0':
                poi_address = sns_info['rawXML']['TimelineObject']['location']['@poiName']
                if not poi_address:
                    poi_address = self.get_address_form_patch((sns_info_x, sns_info_y))

        return (ago_days, poi_address)

    def around_lbs_info(self, ago_time='', author=[], has_pic='', x_y='', distance='', start_page=0, end_page=0):
        # local_flg 0: 附近的人  2：朋友圈
        sns_info_list = []
        if not ago_time:
            ago_time = '1980-01-01'  # 相当于无条件

        if not author:
            author_cond = ".*"
        else:
            author_cond = "^" + author[0] + "$"

        if not has_pic:
            pic_cond = "mediaList"  # 相当于无条件
        else:
            pic_cond = "mediaList.0"  # len(mediaList) >= 0

        if not distance:
            distance = 0

        t = int(time.mktime(time.strptime(ago_time + ' 00:00:00', "%Y-%m-%d %H:%M:%S")))

        print 'search condition:', {"localFlag": AROUND_FLG,
                                    "authorName": {"$regex": author_cond},
                                    "timestamp": {"$gte": t},
                                    pic_cond: {"$exists": 1},
                                    'start_page': start_page,
                                    'end_page': end_page}

        info_list = self.lbs_info.find({"localFlag": AROUND_FLG,
                                        "authorName": {"$regex": author_cond},
                                        "timestamp": {"$gte": t},
                                        pic_cond: {"$exists": 1}}) \
            .sort("timestamp", pymongo.DESCENDING)  # .skip(10 * skip_page).limit(10)
        # l = self.sns_info.find().sort("timestamp", pymongo.DESCENDING)

        for sns_info in info_list:
            distance_flg = False
            d = 0
            (ago_days, poi_address) = self.patch_agoDays_address(sns_info)
            sns_info['ago_days'] = ago_days
            sns_info['poi_address'] = poi_address

            # if not x_y or not distance:
            #     distance_flg = True
            # else:
            #     (x, y) = self.util.convert_str_xy_to_x_y(x_y)
            #     d = self.util.calc_distance((x, y), (sns_info_x, sns_info_y))
            #     if distance > 0 and d <= distance:
            #         distance_flg = True

            # if distance_flg:
            # print u'采集地:', (sns_info_x, sns_info_y), u'选取地:', x_y, u'相距：', d, u'限定：', distance
            sns_info_list.append(sns_info)

        return sns_info_list

    def friends_sns_info(self, ago_time='', friends=[], has_pic=''):
        # local_flg 0: 附近的人  2：朋友圈
        sns_info_list = []
        if not ago_time:
            ago_time = '1980-01-01'  # 相当于无条件

        if not friends or friends[0] == 'all':
            friends_cond = ".*"
        else:
            friends_cond = "^" + friends[0] + "$"

        if not has_pic:
            pic_cond = "mediaList"  # 相当于无条件
        else:
            pic_cond = "mediaList.0"  # len(mediaList) >= 0

        t = int(time.mktime(time.strptime(ago_time + ' 00:00:00', "%Y-%m-%d %H:%M:%S")))
        print 'search condition:', {"localFlag": FRIENDS_FLG,
                                    "authorName": {"$regex": friends_cond},
                                    "timestamp": {"$gte": t},
                                    pic_cond: {"$exists": 1}}

        l = self.sns_info.find({"localFlag": FRIENDS_FLG,
                                "authorName": {"$regex": friends_cond},
                                "timestamp": {"$gte": t},
                                pic_cond: {"$exists": 1}}).sort("timestamp", pymongo.DESCENDING)

        for sns_info in l:
            (ago_days, poi_address) = self.patch_agoDays_address(sns_info)
            sns_info['ago_days'] = ago_days
            sns_info['poi_address'] = poi_address
            sns_info_list.append(sns_info)

        return sns_info_list

    def get_drivers(self):
        return self.db_patch_location.find()

    def get_users(self):
        return self.users.find()

    def get_lbsInfo_list_by_snsId(self, snsId_list):
        lbsInfo_list = []
        l = self.lbs_info.find({'snsId': {'$in': snsId_list}}).sort("timestamp", pymongo.DESCENDING)
        for sns_info in l:
            (ago_days, poi_address) = self.patch_agoDays_address(sns_info)
            sns_info['ago_days'] = ago_days
            sns_info['poi_address'] = poi_address
            lbsInfo_list.append(sns_info)

        return lbsInfo_list

    def get_loginUser_area(self):
        area_list = []
        user = self.util.get_loginUser()
        if user == 'admin':
            area_list = [{"province": "all", "city": "all", "district": "all"}]
        else:
            l = self.users.find({'userName': user})
            for i in l:
                area_list.append({"province": i['province'], "city": i['city'], "district": i['district']})

        return area_list

    def make_userArea_point_js(self):
        '''
            area : {"province": "北京市", "city": "北京市", "district": "海淀区"}
            var weixin_lbs_info =  [
                {"lnglat": ["116.418757", "39.917544"], "name": "东城区"},
                {"lnglat": ["116.366794", "39.915309"], "name": "西城区"},
                {"lnglat": ["116.486409", "39.921489"], "name": "朝阳区"},
            ];
        '''
        area = self.get_loginUser_area()
        # if locations[0]['province'] == 'all': # admin
        l = self.db_patch_location.find()

        fd = open('./static/js/lbsInfo.js', 'w')  # 不能使用‘_’作为文件名
        fd.write('var lbsInfo =  [\n')
        for i in l:
            location = i['location']
            if location != u'None':
                (y, x) = self.util.convert_str_xy_to_x_y(location)
                if x and float(x):
                    fd.write('''    {"lnglat": ["''' + x + '''", "''' + y + '''"], "name": "''' +
                             i['db_patch'] + '''"},\n''')
        fd.write('];\n')
        fd.close()

    def make_userArea_outline_js(self):
        '''
            area : {"province": "北京市", "city": "北京市", "district": "海淀区"}
            var userArea =  "朝阳区";
        '''
        area = self.get_loginUser_area()
        fd = open('./static/js/userArea.js', 'w')  # 不能使用‘_’作为文件名
        fd.write('''var userArea = "''' + area[0]['district'] + '''";\n''')
        fd.close()


class Manager(tornado.web.RequestHandler):
    def get(self):
        print '[info]Manager get() start'
        util = Util()
        y_x = self.get_argument('y_x')
        address = util.convert_xy_to_address(y_x)
        # jsonStr = json.dumps(ret, sort_keys=True)
        print '[info]Manager get()', y_x, '->', address
        # self.write(json.dumps({'address': address}))
        self.write(address)


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.render(
            "index.html",
            title=u"微信采集展示")


class FriendsHandler(tornado.web.RequestHandler):
    def get(self):
        db = DBDriver()
        print '------------------------------- Friends  get  ----------------------------------- '
        friends_list = db.get_friends()
        sns_info_list = db.friends_sns_info()
        print '------------------------------- Friends  get  ----------------------------------- '
        self.render(
            "friends.html",
            title=u"微信-朋友圈",
            sns_info_list=sns_info_list,
            friends_list=friends_list)

    def post(self):
        db = DBDriver()
        ago_time = self.get_argument('ago_time', '')
        authors = self.get_arguments('authors')
        pic_flg = self.get_argument('pic_flg', '')
        print '------------------------------- Friends  post  ----------------------------------- '
        print 'ago_time: ', ago_time, 'authors: ', authors, 'pic_flg: ', pic_flg
        print '------------------------------- Friends  post  ----------------------------------- '
        friends_list = db.get_friends()
        sns_info_list = db.friends_sns_info(ago_time, authors, pic_flg)

        self.render(
            "friends.html",
            title=u"微信-朋友圈",
            sns_info_list=sns_info_list,
            friends_list=friends_list)


class AroundHandler(tornado.web.RequestHandler):
    def create_table(self, lbs_info_list):
        html = '''
        <table id="lbs_info_tab" class="table">
        <thead>
        <tr>
            <th></th>
            <th></th>
        </tr>
        </thead>
        <tbody>
        '''

        for sns_info in lbs_info_list:
            html += '''
            <tr style="border: 1px solid #ccc;">
                <td>
                    <div class="sns_left">
                        <img src="static/images/weixin_logo.png" class="sns_author_logo img-rounded"/>
                    </div>
                </td>
                <td>
                    <div class="sns_right">
                        <div class="sns_author row clearfix">
                        ''' + sns_info["authorName"] + '''
                        </div>
                        <div class="sns_content row clearfix">
                            <small>''' + sns_info["content"] + '''</small>
                        </div>
                        <div class="pull-left sns_image_list row clearfix">'''
            # -----------------------------------------------------------------------------
            for url in sns_info["mediaList"]:
                html += '''<img src="http://read.html5.qq.com/image?src=forum&q=5&r=0&imgflag=7&imageUrl=''' \
                        + url + '''" class="media img-rounded sns_image"/>'''

            html += '''</div>'''
            html += '''
                    <div class="sns_timeLocation row clearfix">
                        <h6><span class="glyphicon glyphicon-time"></span>&nbsp; ''' \
                    + sns_info["ago_days"] + '''&nbsp;&nbsp;&nbsp;
                        <span class="glyphicon glyphicon-screenshot"></span>&nbsp; ''' \
                    + sns_info["poi_address"] + '''
                        </h6>
                    </div>
                    '''
            # -----------------------------------------------------------------------------
            if len(sns_info["likes"]) > 0:
                html += '''
                    <div class="sns_comments row clearfix">
                        <span class="glyphicon glyphicon-heart-empty"></span>'''

            for comment in sns_info["likes"]:
                html += '''<small>&nbsp;&nbsp;''' + comment['userName'] + '''</small>'''

            html += '''</div>'''
            # -----------------------------------------------------------------------------
            if len(sns_info["comments"]) > 0:
                html += '''<div class="sns_comments row clearfix">'''
                for comment in sns_info["comments"]:
                    html += '''<h4>''' + comment['authorName'] + '''<small>&nbsp;&nbsp;''' + \
                            comment['content'] + '''</small></h4>'''
                html += '''</div>'''

            # -----------------------------------------------------------------------------
            html += '''</div>
                </td>
            </tr>'''
            # -----------------------------------------------------------------------------

        # end for
        html += '''</tbody></table>'''
        return html

    def get(self):
        util = Util()
        db = DBDriver()
        session = SessionManager()
        userId = util.get_loginUser()

        init_flg = self.get_argument('init', 'false')
        action = self.get_argument('action', '')

        print '------------------------------- Around  get  -----------------------------------'
        print  'init_flg: ', init_flg, 'action: ', action
        print '------------------------------- Around  get  -----------------------------------'
        authors_list = db.get_around()
        if init_flg == 'true':  # init
            lbs_info_list = db.around_lbs_info()
            session.set_around_search_result(userId, lbs_info_list)
            lbs_info_list = lbs_info_list[:PAGE_NUM]
            self.render(
                "around.html",
                title=u"微信-周围的人",
                lbs_info_list=lbs_info_list,
                authors_list=authors_list)
        else:
            snsId_list = session.get_around_search_result(userId, action)
            lbs_info_list = db.get_lbsInfo_list_by_snsId(snsId_list)
            print 'lbs_info_list:', len(lbs_info_list)
            # self.write("<h1>AAAA</h1>")
            html = self.create_table(lbs_info_list)
            self.write(html)

    def post(self):
        util = Util()
        db = DBDriver()
        session = SessionManager()
        userId = util.get_loginUser()
        snsId_list = []

        ago_time = self.get_argument('ago_time', '')
        authors = self.get_arguments('authors')
        pic_flg = self.get_argument('pic_flg', '')
        x_y = self.get_argument('x_y', '')
        distance = self.get_argument('distance', '')
        start_page = self.get_argument('start_page', '')
        end_page = self.get_argument('end_page', '')

        print '-------------------------------   post  ----------------------------------- '
        print 'ago_time: ', ago_time, 'authors: ', authors, 'pic_flg: ', pic_flg, 'x_y: ', x_y, 'distance: ', distance
        around_list = db.get_around()
        lbs_info_list = db.around_lbs_info(ago_time, authors, pic_flg, x_y, distance, start_page, end_page)
        for snsInfo in lbs_info_list:
            snsId_list.append(snsInfo['snsId'])

        session.set_around_search_result(userId, snsId_list)
        print '-------------------------------   post  ----------------------------------- '

        self.render(
            "around.html",
            title=u"微信-周围的人",
            lbs_info_list=lbs_info_list,
            authors_list=around_list)


class DriversHandler(tornado.web.RequestHandler):
    def get(self):
        db = DBDriver()
        print '-------------------------------   get  -----------------------------------'
        drivers = db.get_drivers()
        users = db.get_users()
        print '-------------------------------   get  -----------------------------------'
        self.render(
            "drivers.html",
            page_title=u"微信-",
            header_text=u"采集结果展示",
            users=users,
            drivers=drivers)

    def post(self):
        pass


class SnsInfoModule(tornado.web.UIModule):
    def render(self, sns_info):
        return self.render_string(
            "modules/sns_info.html",
            sns_info=sns_info,
        )

    def css_files(self):
        return "css/search_result.css"

    def javascript_files(self):
        return "js/search_result.js"


def signal_handler(signum, frame):
    tornado.ioloop.IOLoop.instance().stop()


signal.signal(signal.SIGINT, signal_handler)


class Application(tornado.web.Application):
    def __init__(self):
        settings = dict(
            template_path=os.path.join(os.path.dirname(__file__), "templates"),
            static_path=os.path.join(os.path.dirname(__file__), "static"),
            static_js_path=os.path.join(os.path.dirname(__file__), "static/js"),
            ui_modules={"SnsInfo": SnsInfoModule},
            debug=True,
        )
        handlers = [
            (r"/", MainHandler),
            (r"/friends", FriendsHandler),
            (r"/around", AroundHandler),
            (r"/drivers", DriversHandler),
            (r"/convert_xy_to_address", Manager),
            # (r"/(authors\.js)", tornado.web.StaticFileHandler, dict(path=settings['static_js_path'])),
        ]
        tornado.web.Application.__init__(self, handlers, **settings)


def main():
    db = DBDriver()
    db.make_userArea_point_js()  # 控制前端采集点描绘
    db.make_userArea_outline_js()  # 控制前端行政区轮廓划分

    tornado.locale.set_default_locale('zh_CN')
    tornado.options.parse_command_line()
    http_server = tornado.httpserver.HTTPServer(Application())
    http_server.listen(options.port)
    tornado.ioloop.IOLoop.instance().start()


def patch_address():
    db = DBDriver()
    db.patch_address()


def test():
    db = DBDriver()
    pprint(db.get_friends())


if __name__ == "__main__":
    # test()
    # patch_address()
    main()
