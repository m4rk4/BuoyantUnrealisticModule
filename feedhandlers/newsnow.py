import json, pytz, re
import dateutil.parser
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import datawrapper, rss

import logging

logger = logging.getLogger(__name__)


def convert_string(e):
    t = e
    if not t.startswith("o1`"):
        return False
    t = t.replace("o1`", "").replace("`", "")
    t = t.split("-")
    i = []
    for e in t:
        r = e.split("_")
        n = r.pop(0)
        if n == "a":
            n = "i"
        elif n == "e":
            n = "a"
        elif n == "i":
            n = "e"
        elif n == "j":
            n = "u"
        elif n == "d":
            n = "j"
        elif n == "u":
            n = "d"
        elif n == "w":
            n = "y"
        elif n == "h":
            n = "w"
        elif n == "y":
            n = "h"
        elif n == "l":
            n = "r"
        elif n == ":":
            n = "l"
        elif n == "r":
            n = ":"
        r = n.join(reversed(r))
        i.append(r)
    i = "".join(reversed(i))
    i = i.replace("`u", "_")
    i = i.replace("`d", "-")
    i = i.replace("`x", "`")
    return i


def get_article_info(article_id, stim):
    post_data = {
        "article_ids": [article_id],
        "stim": stim
    }
    data = 'data=' + quote_plus(json.dumps(post_data, separators=(',', ':')))
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "content-type": "application/x-www-form-urlencoded",
        "priority": "u=1, i",
        "sec-ch-ua": "\"Not(A:Brand\";v=\"99\", \"Microsoft Edge\";v=\"133\", \"Chromium\";v=\"133\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin"
    }
    api_json = utils.post_url('https://www.newsnow.com/us/app/v1/article_info', data=data, headers=headers)
    if api_json and api_json['success'] == 1:
        return json.loads(convert_string(api_json['data']))
    return None


def get_page_data(url):
    initial_state = None
    stim = ''

    page_html = utils.get_url_html(url)
    if page_html:
        page_soup = BeautifulSoup(page_html, 'lxml')
        el = page_soup.find('script', string=re.compile(r'__INITIAL_STATE__'))
        if el:
            i = el.string.find('{')
            j = el.string.rfind('};(function()') + 1
            initial_state = json.loads(el.string[i:j])
        else:
            logger.warning('unable to find window.__INITIAL_STATE__ in ' + url)
        el = page_soup.find('script', string=re.compile(r'"sTim":'))
        if el:
            m = re.search(r'"sTim":\s?\'([^\']+)', el.string)
            if m:
                stim = m.group(1)
        if not stim:
            logger.warning('unable to find sTim in ' + url)
    return initial_state, stim


def get_content(url, args, site_json, save_debug=False, article_json=None):
    initial_state, stim = get_page_data(url)
    if not initial_state:
        return None
    if save_debug:
        utils.write_file(initial_state, './debug/debug.json')

    page_data = initial_state['page']['clickthroughPageData']
    item = {}
    item['id'] = page_data['articleId']
    item['url'] = page_data['url']
    item['title'] = page_data['title']

    item['image'] = page_data['img']

    if article_json:
        # Seems to be local time
        tz_loc = pytz.timezone(config.local_tz)
        dt_loc = datetime.fromtimestamp(int(article_json['timestamp']))
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt, False)

        item['author'] = {
            "name": article_json['pubName']
        }
        item['authors'] = []
        item['authors'].append(item['author'])

        if article_json.get('tags'):
            item['tags'] = [x['title'] for x in article_json['tags']]
    else:
        article_info = get_article_info(item['id'], stim)
        if article_info:
            if save_debug:
                utils.write_file(article_info, './debug/article.json')

            dt = dateutil.parser.parse(article_info[item['id']]['PublicationTimeUTC'].replace('d', '-')).replace(tzinfo=timezone.utc)
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt, False)

            item['author'] = {
                "name": article_info[item['id']]['Publication']['Name']
            }
            item['authors'] = []
            item['authors'].append(item['author'])

    item['content_html'] = utils.add_embed(item['url'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    initial_state, stim = get_page_data(url)
    if not initial_state:
        return None
    if save_debug:
        utils.write_file(initial_state, './debug/feed.json')

    newsnow_articles = None
    if stim:
        post_data = {
            "page": initial_state['page']['frozenPageString'],
            "tr_mnids": [],
            "tr_searches": [],
            "stim": stim,
            "UseAlternativeTheme": False,
            "TTOutput": "default"
        }
        data = 'data=' + quote_plus(json.dumps(post_data, separators=(',', ':')))
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
            "content-type": "application/x-www-form-urlencoded",
            "priority": "u=1, i",
            "sec-ch-ua": "\"Not(A:Brand\";v=\"99\", \"Microsoft Edge\";v=\"133\", \"Chromium\";v=\"133\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin"
        }
        api_json = utils.post_url('https://www.newsnow.com/us/app/v1/articles', data=data, headers=headers)
        if api_json:
            # if save_debug:
            #     utils.write_file(api_json, './debug/debug.json')
            if api_json['success'] == 1:
                newsnow_articles = json.loads(convert_string(api_json['data']))
                utils.write_file(newsnow_articles, './debug/articles.json')

    if not newsnow_articles:
        newsnow_articles = initial_state['news']

    params = parse_qs(urlsplit(url).query)
    if not params:
        news_articles = newsnow_articles['top']
    elif params.get('type'):
        if params['type'][0] == 'ln':
            if newsnow_articles.get('latest'):
                news_articles = newsnow_articles['latest']
            elif newsnow_articles.get('latestArticles'):
                news_articles = newsnow_articles['latestArticles']
        elif params['type'][0] == 'ts':
            news_articles = newsnow_articles['mostRead']

    for news in news_articles:
        if news['type'] == 'article':
            item = get_content(news['url'], args, site_json, save_debug, news)
        elif news['type'] == 'cluster':
            article = news['articles'][0]
            item = get_content(article['url'], args, site_json, save_debug, article)
            item['content_html'] += '<h2>Related articles</h2>'
            for article in news['articles']:
                it = get_content(article['url'], args, site_json, save_debug, article)
                if it:
                    item['content_html'] += it['content_html'] + '<div>&nbsp;</div>'

    return None