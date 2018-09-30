# -*- coding: utf-8 -*-
"""
Created on Fri Aug 31 16:36:32 2018

@author: yangwn
"""

import scrapy
from bs4 import BeautifulSoup
from scrapy import log
from datetime import timedelta
import re
from spider_news_all.items import SpiderNewsAllItem
import datetime
import time
#from tomd import Tomd
import MySQLdb
import threading
from spider_news_all.config import SpiderNewsAllConfig


class InfoqSpider(scrapy.Spider):
    name = "infoq"
    site_name = "infoq"
    allowed_domains = ["infoq.com"]###?
    start_urls = (
            "http://www.infoq.com/cn/ai-ml-data-eng/news/0",
            "http://www.infoq.com/cn/bigdata/news/0",
            "http://www.infoq.com/cn/cloud-computing/news/0",
            "http://www.infoq.com/cn/qukuailian/news/0",
            "http://www.infoq.com/cn/ai-ml-data-eng/articles/0",
            "http://www.infoq.com/cn/bigdata/articles/0",
            "http://www.infoq.com/cn/cloud-computing/articles/0",
            "http://www.infoq.com/cn/qukuailian/articles/0",
            "http://www.infoq.com/cn/development/news/0",
            "http://www.infoq.com/cn/architecture-design/news/0",
            "http://www.infoq.com/cn/development/articles/0",
            "http://www.infoq.com/cn/architecture-design/articles/0",
    )
    handle_httpstatus_list = [521]###?
 
    FLAG_INTERRUPT = False
 
    lock = threading.RLock()
    cfg = SpiderNewsAllConfig.news_db_addr
    conn=MySQLdb.connect(host= cfg['host'],user=cfg['user'], passwd=cfg['password'], db=cfg['db'], autocommit=True)
    conn.set_character_set('utf8')
    cursor = conn.cursor()
    cursor.execute('SET NAMES utf8;')
    cursor.execute('SET CHARACTER SET utf8;')
    cursor.execute('SET character_set_connection=utf8;')

    
    def __init__(self):
        self.lock.acquire()
        self.cursor.execute("SELECT start_url, latest_url FROM url_record WHERE site_name='%s'"%self.site_name)
        self.record_url = dict(self.cursor.fetchall())
        self.lock.release()
        for start_url in [re.search("(.*)/\d+",url).group(1) for url in self.start_urls]:
            if self.record_url.get(start_url)==None:
                self.record_url.setdefault(start_url,None)
                self.lock.acquire()
                self.cursor.execute("INSERT INTO url_record (site_name, start_url, latest_url) VALUES ('%s','%s','%s')"%(self.site_name,start_url,None))
                self.lock.release()
        self.updated_record_url = self.record_url.copy()


    def get_type_from_url(self, url,url_news):
        if 'ai-ml-data-eng' in url:
            return u'人工智能'
        elif 'bigdata' in url:
            return u'大数据'
        elif 'cloud-computing' in url:
            return u'云计算'
        elif 'qukuailian' in url:
            return u'区块链'
        else:
            return u'综合新闻'



    def parse(self, response):
        log.msg("Start to parse page " + response.url, level=log.INFO)
        url = response.url
        start_url = re.search("(.*)/\d+",url).group(1)   
        items = []
        time_now = datetime.datetime.now()
        try:
            response = response.body
            soup = BeautifulSoup(response)
            links = soup.find_all("div",class_ = ["news_type_block","news_type_block last","new_type1","news_type1 last","news_type2 full_screen"])
        except:
            items.append(self.make_requests_from_url(url))
            log.msg("Page " + url + " parse ERROR, try again !", level=log.ERROR)
            return items
        need_parse_next_page = True
        if len(links) > 0:
            is_first = True
            for i in range(0, len(links)):
                    url_news = links[i].find("h2").find("a").get("href").strip() 
                    if not re.match("http",url_news): 
                        url_news = "http://www.infoq.com"+url_news
                        
                    if url in self.start_urls and is_first:
                        self.updated_record_url[start_url] = url_news
                        is_first = False
                    if url_news == self.record_url[start_url]:
                        need_parse_next_page = False
                        break

                    type3 = self.get_type_from_url(url,url_news)
                    
                    day = re.findall(u"(\d+年\d+月\d+日)",links[i].find("span",class_ = "author").text)[-1].strip() 
                    day = self.time_convert(day,time_now)
                    title = links[i].find("h2").get_text().strip() 
                    items.append(self.make_requests_from_url(url_news).replace(callback=self.parse_news, meta={'type3': type3, 'day': day, 'title': title}))
            
            if "articles" in url:
                page_lag = 12
            elif "news" in url:
                page_lag = 15
            page = int(re.search("(.*)/(\d+)",url).group(2))
            if need_parse_next_page and page < 2*page_lag:#need_parse_next_page:
                page += page_lag
                page_next = re.sub("\d+",str(page),url)
                if need_parse_next_page:
                    items.append(self.make_requests_from_url(page_next))
            else:
                self.lock.acquire()
                self.cursor.execute("UPDATE url_record SET latest_url='%s' WHERE site_name='%s' AND start_url='%s'"%(self.updated_record_url[start_url],self.site_name,start_url))
                self.lock.release()
            return items


    def parse_news(self, response):
        log.msg("Start to parse news " + response.url, level=log.INFO)
        item = SpiderNewsAllItem()
        day = title = type3 = keywords = url = article = ''
        url = response.url
        url = re.sub('(?P<value>\?useSponsorshipSuggestions=true$)','',url)
        day = response.meta['day']
        title = response.meta['title']
        type3 = response.meta['type3']
        response = response.body
        soup = BeautifulSoup(response)
        try:
            content_paragraph = soup.find("div",class_="text_info")
            content = []
            for tag in content_paragraph.find("div",class_="clear").previous_siblings:
                content.insert(0,tag)
            article = [str(tag) for tag in content]                            
            markdown = "".join((article)).decode('utf-8')
            article = BeautifulSoup(''.join([str(tag) for tag in article])).get_text().strip()
        except:
            log.msg("News " + title + " dont has article!", level=log.INFO)
        item['title'] = title
        item['day'] = day
        item['type1'] = u'源站资讯'
        item['type2'] = u'InfoQ'
        item['type3'] = type3
        item['url'] = url
        item['keywords'] = keywords
        item['article'] = article
        item['site'] = 'InfoQ'
        item['markdown'] = markdown
        return item

        
    def time_convert(self,old_string,time_now):
        if type(old_string)==unicode:
            old_string = old_string.encode("utf-8")
        old_string = re.sub("：",":",old_string)
        new_string = old_string
        if re.match("今天",old_string):
            new_string = re.sub("今天",time_now.strftime("%Y-%m-%d"),old_string)
        elif re.match("昨天",old_string):
            new_string = re.sub("昨天",(time_now + timedelta(days = -1)).strftime("%Y-%m-%d"),old_string)
        elif re.match("前天",old_string):
            new_string = re.sub("前天",(time_now + timedelta(days = -2)).strftime("%Y-%m-%d"),old_string)
        elif re.search("(\d+)天前",old_string):
            delta_day = int(re.search("(\d+)天前",old_string).group(1))
            new_string = re.sub("\d+天前",(time_now + timedelta(days = -delta_day)).strftime("%Y-%m-%d"),old_string)
        elif re.search("(\d+)小时前",old_string):
            delta_hour = int(re.search("(\d+)小时前",old_string).group(1))
            new_string = re.sub("\d+小时前",(time_now + timedelta(hours = -delta_hour)).strftime("%Y-%m-%d %H:%M"),old_string)
        elif re.search("(\d+)分钟前",old_string):
            delta_min =  int(re.search("(\d+)分钟前",old_string).group(1))
            new_string = (time_now-datetime.timedelta(minutes=delta_min)).strftime("%Y-%m-%d %H:%M")
        elif re.match("\d+/\d+",old_string):
            if len(re.findall("/",old_string)) == 1:
                month = int(re.match("(\d+)/(\d+)",old_string).group(1))
                date = int(re.match("(\d+)/(\d+)",old_string).group(2))
                if month > time_now.month:
                    year = time_now.year-1
                else:
                    year = time_now.year
                new_string = re.sub("\d+/\d+",datetime.datetime(year,month,date).strftime("%Y-%m-%d"),old_string)
            elif len(re.findall("/"),old_string) == 2:
                month = int(re.match("(\d+)/(\d+)/(\d+)",old_string).group(2))
                date = int(re.match("(\d+)/(\d+)/(\d+)",old_string).group(3))
                if len(re.match("(\d+)/(\d+)/(\d+)",old_string).group(1))==2:
                    year = time_now.year/100*100+int(re.match("(\d+)/(\d+)/(\d+)",old_string).group(1))
                elif len(re.match("(\d+)/(\d+)/(\d+)",old_string).group(1))==4:
                    year = int(re.match("(\d+)/(\d+)/(\d+)",old_string).group(1))
                new_string = re.sub("\d+/\d+/\d+",datetime.datetime(year,month,date).strftime("%Y-%m-%d"),old_string)
        elif re.match("\d+年\d+月\d+日",old_string):
            year = int(re.match("(\d+)年(\d+)月(\d+)日",old_string).group(1))
            month = int(re.match("(\d+)年(\d+)月(\d+)日",old_string).group(2))
            date = int(re.match("(\d+)年(\d+)月(\d+)日",old_string).group(3))
            new_string = re.sub("\d+年\d+月\d+日",datetime.datetime(year,month,date).strftime("%Y-%m-%d"),old_string)
        elif re.match("刚刚",old_string):
            new_string = time_now.strftime("%Y-%m-%d %H:%M:%S")
        
        if re.match("\d{4}-\d+-\d+ \d+:\d+:\d+",new_string):
            time_stamp = int(time.mktime(time.strptime(new_string,"%Y-%m-%d %H:%M:%S")))
        elif re.match("\d{4}-\d+-\d+ \d+:\d+",new_string):
            time_stamp = int(time.mktime(time.strptime(new_string,"%Y-%m-%d %H:%M")))
        elif re.match("\d{4}-\d+-\d+",new_string):
            time_stamp = int(time.mktime(time.strptime(new_string,"%Y-%m-%d")))

        return time_stamp
        