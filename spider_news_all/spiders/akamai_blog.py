# -*- coding: utf-8 -*-
"""
Created on Tue Sep  4 10:34:45 2018

@author: yangwn
"""

import scrapy
from bs4 import BeautifulSoup
from scrapy import log
from datetime import date, timedelta
import re
from spider_news_all.items import SpiderNewsAllItem
import datetime
import time
from tomd import Tomd
import MySQLdb
import threading
from spider_news_all.config import SpiderNewsAllConfig


class AkamaiBlogSpider(scrapy.Spider):
    name = "akamai_blog"
    site_name = "akamai_blog"
    allowed_domains = ["akamai.com"]###?
    start_urls = (
            "https://blogs.akamai.com/",
    )
    handle_httpstatus_list = [521]###?
 

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
        for start_url in self.start_urls:
            if self.record_url.get(start_url)==None:
                self.record_url.setdefault(start_url,None)
                self.lock.acquire()
                self.cursor.execute("INSERT INTO url_record (site_name, start_url, latest_url) VALUES ('%s','%s','%s')"%(self.site_name,start_url,None))
                self.lock.release()
        self.updated_record_url = self.record_url.copy()

    
    def time_convert(self,old_string,time_now):
        if type(old_string)==unicode:
            old_string = old_string.encode("utf-8")
        old_string = re.sub("：",":",old_string)
        new_string = old_string
        #new_stirng = time.strftime("%Y-%m-%d %H:%M:%S")
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
            new_string = re.sub("\d+小时前",(time_now + timedelta(hours = -delta_hour)).strftime("%Y-%m-%d"),old_string)
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
                if len(re.match("(\d+)/(\d+)/(\d+)","old_string").group(1))==2:
                    year = time_now.year/100*100+int(re.match("(\d+)/(\d+)/(\d+)",old_string).group(1))
                elif len(re.match("(\d+)/(\d+)/(\d+)","old_string").group(1))==4:
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

    


    def parse_news(self, response):
        log.msg("Start to parse news " + response.url, level=log.INFO)
        item = SpiderNewsAllItem()
        day = title = _type = keywords = url = article = ''
        url = response.url
        day = response.meta['day']
        title = response.meta['title']
        _type = response.meta['_type']
        response = response.body
        soup = BeautifulSoup(response)
#        try:
#            items_keywords = soup.find(class_='ar_keywords').find_all('a')
#            for i in range(0, len(items_keywords)):
#                keywords += items_keywords[i].text.strip() + ' '
#        except:
#            log.msg("News " + title + " dont has keywords!", level=log.INFO)
        
        try:
            content = soup.find("div","asset-content entry-content")
            article = content.text.strip().replace(u'\xc2\xa0', u' ')
            markdown = Tomd(unicode(content).replace(u"\xc2\xa0",u" ")).markdown
        except:
            log.msg("News " + title + " dont has article!", level=log.INFO)
        item['title'] = title
        item['day'] = day
        item['_type'] = _type
        item['url'] = url
        item['keywords'] = keywords
        item['article'] = article
        item['site'] = 'Akamai'
        item['markdown'] = markdown
        return item


    def parse(self, response):
        log.msg("Start to parse page " + response.url, level=log.INFO)
        url = response.url
#        if url in self.start_urls:
#            self.crawl_index[self.start_urls.index(url)]=True
#            self.all_crawled = not False in self.crawl_index
        start_url = re.search("(.*)/\d+",url).group(1)   
        items = []
        time_now = datetime.datetime.now()
        try:
            response = response.body
            soup = BeautifulSoup(response)
#            lists = soup.find(class_='list')
            links = soup.find_all("div",class_ = ["news_type_block","news_type_block last","new_type1","news_type1 last","news_type2 full_screen"])
        except:
            items.append(self.make_requests_from_url(url))
            log.msg("Page " + url + " parse ERROR, try again !", level=log.ERROR)
            return items
        need_parse_next_page = True
        if len(links) > 0:
            is_first = True
            for i in range(0, len(links)):
                    url_news = links[i].find("h2").find("a").get("href") #获取新闻内容页链接
#                    if not re.match("http",url_news): #必要时对不完整的新闻链接作补充修改
#                        url_news = "http://www.infoq.com"+url_news
                        
                    if url in self.start_urls and is_first:
                        self.updated_record_url[start_url] = url_news
                        is_first = False
                    if url_news == self.record_url[start_url]:
                        need_parse_next_page = False
                        break

                    _type = u"友商官方"
                    
                    day = links[i].find("abbr",class_="published").get("title") ##获取新闻发布时间
                    day=re.sub("-05:00$","",re.sub("T"," ",day))    #时区
                    day = (datetime.datetime.strptime(day, "%Y-%m-%d %H:%M:%S")+timedelta(hours = (8-(-5)))).strftime("%Y-%m-%d %H:%M:%S")
                    day = self.time_convert(day,time_now)
                    title = links[i].find("h2").text #获取首页新闻标题
                    items.append(self.make_requests_from_url(url_news).replace(callback=self.parse_news, meta={'_type': _type, 'day': day, 'title': title}))
            
            if url == 'https://blogs.akamai.com/':
                page = 1
            else:
                page = int(re.search("index(\d+).html",url).group(1))
            
            page = int(re.search("(.*)/(\d+)",url).group(2))
            if need_parse_next_page and page < 2:#need_parse_next_page:
                page += 1
                page_next = re.sub("\d+",str(page),url)
                if need_parse_next_page:
                    items.append(self.make_requests_from_url(page_next))
            else:
                self.lock.acquire()
                self.cursor.execute("UPDATE url_record SET latest_url='%s' WHERE site_name='%s' AND start_url='%s'"%(self.updated_record_url[start_url],self.site_name,start_url))
                self.lock.release()
                        
#            if (soup.find('a', text=u'下一页')['href'].startswith('http://')):
#                page_next = soup.find('a', text=u'下一页')['href']
#                if need_parse_next_page:
#                    items.append(self.make_requests_from_url(page_next))
            
            return items
        
        