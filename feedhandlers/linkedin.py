import html, json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs, urlsplit, quote_plus

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)

def get_content_item(soup, reshare_item, args, site_json, save_debug):
    item = {}
    el = soup.find('link', attrs={"rel": "canonical"})
    if el:
        item['url'] = el['href']

    el = soup.find('meta', attrs={"property": "og:title"})
    if el:
        item['title'] = el['content']

    item['content_html'] = '<table style="width:480px; margin-left:auto; margin-right:auto; padding:4px; border:1px solid black;">'
    el = soup.find('a', class_='share-update-card__actor-text-link')
    if el:
        item['author'] = {}
        item['author']['name'] = el.get_text().strip()
        author_url = el['href']
        el = soup.find('img', class_='share-update-card__actor-image')
        if el:
            avatar = html.unescape(el['data-delayed-url'])
        else:
            avatar = 'https://static-exp1.licdn.com/sc/h/9c8pery4andzj6ohjkjp54ma2'
        avatar = '{}/image?url={}&height=48&mask=ellipse'.format(config.server, quote_plus(avatar))
        it = soup.find('time', class_='share-update-card__post-date')
        if it:
            post_date = it.get_text().strip()
        else:
            post_date = ''
        item['content_html'] += '<tr><td style="width:48px;"><img src="{}"/></td><td><a href="{}"><strong>{}</strong></a><br/><small>{}</small></td></tr>'.format(avatar, author_url, item['author']['name'], post_date)

    el = soup.find('p', class_='share-update-card__update-text')
    if el:
        for it in el.find_all('a'):
            href = it['href']
            it.attrs = {}
            split_url = urlsplit(href)
            query = parse_qs(split_url.query)
            if query.get('session_redirect'):
                href = query['session_redirect'][0]
            it['href'] = href
        item['content_html'] += '<tr><td colspan="2">{}</td></tr>'.format(str(el).replace('\n', '<br/>'))

    for el in soup.find_all('img', class_='share-images__image'):
        item['content_html'] += '<tr><td colspan="2"><img src="{}" width="100%"/></td></tr>'.format(html.unescape(el['data-delayed-url']))

    for el in soup.find_all('video', class_='share-native-video__node'):
        data_sources = json.loads(el['data-sources'])
        #utils.write_file(video_json, './debug/video.json')
        video = utils.closest_dict(data_sources, 'data-bitrate', 0)
        video_html = utils.add_video(video['src'], video['type'], html.unescape(el['data-poster-url']))
        item['content_html'] += '<tr><td colspan="2">{}</td></tr>'.format(video_html)

    el = soup.find(class_='share-article')
    if el:
        item['content_html'] += '<tr><td colspan="2">'
        it = el.find('img', class_='share-article__image')
        if it:
            item['content_html'] += '<img src="{}" width="100%"/>'.format(html.unescape(it['data-delayed-url']))
        it = el.find('a', class_='share-article__title-link')
        if '/redirect' in it['href']:
            split_url = urlsplit(it['href'])
            query = parse_qs(split_url.query)
            href = query['url'][0]
        else:
            href = it['href']
        title = it.get_text().strip()
        it = el.find(class_='share-article__subtitle')
        subtitle = it.get_text().strip()
        item['content_html'] += '<h3 style="margin-top:0; margin-bottom:0;"><a href="{}">{}</a></h3><small>{}</small></td></tr>'.format(href, title, subtitle)

    if reshare_item:
        item['content_html'] += '<tr><td colspan="2">{}</td></tr>'.format(reshare_item['content_html'])

    if item.get('url'):
        item['content_html'] += '<tr><td colspan="2"><a href="{}"><small>Open in LinkedIn</small></a></td></tr>'.format(item['url'])

    item['content_html'] += '</table>'
    return item


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    if split_url.path.startswith('/embed/'):
        embed_url = url
    elif '/urn:li:activity:' in split_url.path:
        embed_url = 'https://www.linkedin.com/embed' + split_url.path
    else:
        m = re.search(r'-(\d+)-.{4}$', split_url.path)
        if not m:
            logger.warning('unhandled LinkedIn url ' + url)
            return None
        embed_url = 'https://www.linkedin.com/embed/feed/update/urn:li:activity:' + m.group(1)
    embed_html = utils.get_url_html(embed_url)
    if not embed_html:
        return None
    if save_debug:
        utils.write_file(embed_html, './debug/debug.html')

    soup = BeautifulSoup(embed_html, 'html.parser')

    el = soup.find(class_='share-update-card--reshare')
    if el:
        reshare_item = get_content_item(el.extract(), None, args, site_json, save_debug)
    else:
        reshare_item = None

    item = get_content_item(soup, reshare_item, args, site_json, save_debug)
    return item
