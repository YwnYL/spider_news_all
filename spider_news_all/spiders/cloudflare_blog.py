# -*- coding: utf-8 -*-
"""
Created on Wed Sep  5 15:28:41 2018

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
from tomd import Tomd
import MySQLdb
import threading
from spider_news_all.config import SpiderNewsAllConfig
import HTMLParser


class CloudflareSpider(scrapy.Spider):
    name = "cloudflare_blog"
    site_name = "cloudflare_blog"
    allowed_domains = ["cloudflare.com"]
    start_urls = (
            "https://blog.cloudflare.com",
    )
    handle_httpstatus_list = [521]
 

    lock = threading.RLock()
    cfg = SpiderNewsAllConfig.news_db_addr
    conn=MySQLdb.connect(host= cfg['host'],user=cfg['user'], passwd=cfg['password'], db=cfg['db'], autocommit=True)
    conn.set_character_set('utf8')
    cursor = conn.cursor()
    cursor.execute('SET NAMES utf8;')
    cursor.execute('SET CHARACTER SET utf8;')
    cursor.execute('SET character_set_connection=utf8;')
    html_parser = HTMLParser.HTMLParser()
    
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

    def number(self,matched):
        value = int(matched.group('value'))
        return str(value)
    

    def parse_news(self, response):
        log.msg("Start to parse news " + response.url, level=log.INFO)
        item = SpiderNewsAllItem()
        day = title = _type = keywords = url = article = ''
        url = response.url
        day = response.meta['day']
        title = response.meta['title']
        _type = response.meta['_type']
        response = response.body
        soup = BeautifulSoup(response,"lxml")
        try:
            items_keywords = soup.find("div",class_='footer-tags').find_all('a')
            keywords = [tag.text.strip() for tag in items_keywords]
            keywords = ','.join(keywords)
        except:
            log.msg("News " + title + " dont has keywords!", level=log.INFO)
        
        try:
            content = soup.find("div",class_ = "post-content")
            article = content.text.strip()
            markdown = str(content).decode('utf-8') #html code
#            markdown = self.html_parser.unescape(Tomd(str(content)).markdown.decode("utf-8"))
        except:
            log.msg("News " + title + " dont has article!", level=log.INFO)
        item['title'] = title
        item['day'] = day
        item['_type'] = _type
        item['url'] = url
        item['keywords'] = keywords
        item['article'] = article
        item['site'] = 'Cloudflare'
        item['markdown'] = markdown
        return item


    def parse(self, response):
        log.msg("Start to parse page " + response.url, level=log.INFO)
        url = response.url
        start_url = self.start_urls[0]
        items = []
        try:
            response = response.body
            soup = BeautifulSoup(response,"lxml")
            links = soup.find_all("article")
        except:
            items.append(self.make_requests_from_url(url))
            log.msg("Page " + url + " parse ERROR, try again !", level=log.ERROR)
            return items
        need_parse_next_page = True
        if len(links) > 0:
            is_first = True
            for i in range(0, len(links)):
                    url_news = links[i].find("h2").find("a").get("href") 
                    if not re.match("http",url_news): 
                        url_news = start_url + url_news
                    if url in self.start_urls and is_first:
                        self.updated_record_url[start_url] = url_news
                        is_first = False
                    if url_news == self.record_url[start_url]:
                        need_parse_next_page = False
                        break

                    _type = u"友商官方"
                    day = links[i].find("time").text 
                    day = re.sub('(?P<value>\d+)(nd|st|rd|th)', self.number, day)
                    day = datetime.datetime.strptime(day, "%B %d, %Y %I:%M%p")+timedelta(hours = 8) #convert time format and time-zone
                    day = int(time.mktime(day.timetuple())) # convert to timestamp
                    title = links[i].find("h2").text 
                    items.append(self.make_requests_from_url(url_news).replace(callback=self.parse_news, meta={'_type': _type, 'day': day, 'title': title}))
            
            if url == start_url or url == start_url+"/":
                page = 1
            else:
                page = int(re.search("/page/(\d+)",url).group(1))
            
            if need_parse_next_page and page < 3:#need_parse_next_page:
                page += 1
                if page == 2:
                    page_next = 'https://blog.cloudflare.com/page/2/'
                else:
                    page_next = re.sub("\d+",str(page),url)
                if need_parse_next_page:
                    items.append(self.make_requests_from_url(page_next))
            else:
                self.lock.acquire()
                self.cursor.execute("UPDATE url_record SET latest_url='%s' WHERE site_name='%s' AND start_url='%s'"%(self.updated_record_url[start_url],self.site_name,start_url))
                self.lock.release()
            return items
        
        