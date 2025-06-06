import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import unquote_plus, urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    if split_url.netloc == 'embed.tagboard.com':
        # https://embed.tagboard.com/9315
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": "en-US,en;q=0.9",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "referer": args['referer'],
            "sec-ch-ua": "\"Chromium\";v=\"116\", \"Not)A;Brand\";v=\"24\", \"Microsoft Edge\";v=\"116\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "iframe",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "cross-site",
            "upgrade-insecure-requests": "1",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36 Edg/116.0.1938.69"
        }
        page_html = utils.get_url_html(url, headers=headers)
        #utils.write_file(page_html, '/debug/debug.html')
        soup = BeautifulSoup(page_html, 'html.parser')
        el = soup.find('iframe', class_='smart-panel-iframe')
        if not el:
            return None
        panels_url = el['src']
    elif split_url.netloc == 'panels.tagboard.com':
        panels_url = url
    else:
        logger.warning('unhandled tagboard url ' + url)
        return None

    page_html = utils.get_url_html(panels_url)
    m = re.search(r'"_id":"([^"]+)"', page_html)
    if not m:
        logger.warning('unable to determine poll id in ' + panels_url)
        return None

    poll_json = utils.get_url_json('https://polls.tagboard.com/polls/{}/display'.format(m.group(1)))
    if save_debug:
        utils.write_file(poll_json, './debug/poll.json')
    item = {}
    item['id'] = poll_json['result']['_id']
    item['url'] = panels_url
    if not poll_json:
        return None
    item['title'] = poll_json['result']['title']
    dt = datetime.fromisoformat(poll_json['result']['start_time'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['content_html'] = '<hr/><div style="width:80%; margin-right:auto; margin-left:auto; margin-right:auto; border:1px solid black; border-radius:10px; padding:10px;"><h2><a href="{}">Poll: {}</a></h2>'.format(item['url'], poll_json['result']['cta'])
    for it in poll_json['result']['options']:
        pct = int(it['count'] / poll_json['result']['total'] * 100)
        if pct >= 50:
            item['content_html'] += '<div style="border:1px solid black; border-radius:10px; display:flex; justify-content:space-between; padding-left:8px; padding-right:8px; margin-bottom:8px; background:linear-gradient(to right, lightblue {}%, white {}%);"><p>{}</p><p>{}%</p></div>'.format(pct, 100 - pct, it['value'], pct)
        else:
            item['content_html'] += '<div style="border:1px solid black; border-radius:10px; display:flex; justify-content:space-between; padding-left:8px; padding-right:8px; margin-bottom:8px; background:linear-gradient(to left, white {}%, lightblue {}%);"><p>{}</p><p>{}%</p></div>'.format(100 - pct, pct, it['value'], pct)

    dt = datetime.fromisoformat(poll_json['result']['end_time'].replace('Z', '+00:00'))
    diff = dt - datetime.utcnow().replace(tzinfo=timezone.utc)
    if diff.total_seconds() > 0:
        item['content_html'] += '<div><small>Poll is open until {} &bull; {} votes</small></div></div>'.format(utils.format_display_date(dt, date_only=True), poll_json['result']['total'])
    else:
        item['content_html'] += '<div><small>Poll is closed &bull; {} votes</small></div></div>'.format(poll_json['result']['total'])
    return item