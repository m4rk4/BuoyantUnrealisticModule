import json
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright
from urllib.parse import urlencode, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "cookie": site_json['cookie'],
        "pragma": "no-cache",
        "sec-ch-ua": "\"Microsoft Edge\";v=\"117\", \"Not;A=Brand\";v=\"8\", \"Chromium\";v=\"117\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36 Edg/117.0.2045.60"
    }
    page_html = utils.get_url_html(url, headers)
    if not page_html:
        return None
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')
    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('script', id='__NUXT_DATA__')
    if not el:
        logger.warning('unable to find __NUXT_DATA__ in ' + url)
        #el = soup.find('script', src=re.compile(r'_Incapsula_Resource'))
        with sync_playwright() as playwright:
            engine = playwright.chromium
            browser = engine.launch()
            context = browser.new_context()
            page = context.new_page()
            page.goto('https://www.bizjournals.com')
            cookies = context.cookies()
            browser.close()
        cookie = ''
        for it in cookies:
            if it['name'].startswith('visid_incap') or it['name'].startswith('incap_ses'):
                cookie += '{}={}; '.format(it['name'], it['value'])
        if not cookie:
            logger.warning('unable to get new incap cookies for ' + url)
            return None
        site_json['cookie'] = cookie.strip()
        logger.debug('updating bizjournals.com cookies')
        utils.update_sites(url, site_json)
        headers['cookie'] = site_json['cookie']
        page_html = utils.get_url_html(url, headers)
        if not page_html:
            return None
        if save_debug:
            utils.write_file(page_html, './debug/debug.html')
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('script', id='__NUXT_DATA__')
        if not el:
            logger.warning('unable to find __NUXT_DATA__ in ' + url)

    if save_debug:
        nuxt_data = json.loads(el.string)
        utils.write_file(nuxt_data, './debug/nuxt.json')

    item = {}
    el = soup.find('script', attrs={"type": "application/ld+json"})
    if el:
        ld_json = json.loads(el.string)
        if save_debug:
            utils.write_file(ld_json, './debug/debug.json')
        #item['id'] =
        item['url'] = ld_json['url']
        item['title'] = ld_json['headline']

        dt = datetime.fromisoformat(ld_json['datePublished']).astimezone(timezone.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

        item['author'] = {"name": ld_json['author']['name']}

        if ld_json.get('keywords'):
            item['tags'] = [it.strip() for it in ld_json['keywords'].split(',')]

        item['content_html'] = ''
        if ld_json.get('description'):
            item['summary'] = ld_json['description']

        if ld_json.get('image'):
            if isinstance(ld_json['image'], list):
                image = ld_json['image'][0]
            else:
                image = ld_json['image']
            item['_image'] = image['url']
            item['content_html'] += utils.add_image(item['_image'], image.get('caption'))

    body = soup.find(attrs={"data-dev": "Content Body"})
    if body:
        for el in body.find_all(attrs={"data-dev": "Movable Ad"}):
            el.decompose()

        for el in body.find_all(attrs={"position": "article:incontentlink"}):
            el.decompose()

        for el in body.find_all(attrs={"data-dev": "Media Image"}):
            img_src = ''
            it = el.find('img')
            if it:
                if it.get('srcset'):
                    img_src = utils.image_from_srcset(it['srcset'], 1000)
                elif it.get('src'):
                    img_src = it['src']
            if img_src:
                captions = []
                it = el.find('figcaption')
                if it:
                    captions.append(it.get_text())
                it = el.find('text-xxs')
                if it:
                    captions.append(it.get_text())
                new_html = utils.add_image(img_src, ' | '.join(captions))
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unknown image source in ' + item['url'])

        for el in body.find_all(class_='embed'):
            new_html = ''
            it = el.find(class_='infogram-embed')
            if it:
                new_html = utils.add_embed('https://infogram.com/' + it['data-id'])
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled embed in ' + item['url'])

        item['content_html'] += body.decode_contents()
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
