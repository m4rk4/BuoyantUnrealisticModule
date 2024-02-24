import json, re, tldextract
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

import utils
from feedhandlers import brightcove, rss

import logging

logger = logging.getLogger(__name__)


def resize_image(image, width=1000):
    if image.get('fileName'):
        return 'https://static.ffx.io/images/q_80,f_auto,w_{}/{}'.format(width, image['fileName'])
    else:
        return 'https://static.ffx.io/images/q_80,f_auto,w_{}/{}'.format(width, image['id'])


def add_image(image, width=1000):
    captions = []
    if image.get('caption') and image['caption'].strip() and image['caption'] != '<bf>':
        captions.append(image['caption'].strip())
    if image.get('credit') and image['credit'].strip():
        captions.append(image['credit'].strip())
    return utils.add_image(resize_image(image, width), ' | '.join(captions))


def add_video(url, video_id):
    bc_account = ''
    bc_player = ''
    page_html = utils.get_url_html(url)
    if not page_html:
        return ''

    soup = BeautifulSoup(page_html, 'html.parser')
    el = soup.find('video')
    if el:
        if el.get('data-account'):
            bc_account = el['data-account']
        if el.get('data-player'):
            bc_player = el['data-player']
        if not video_id and el.get('data-video-id'):
            video_id = el['data-video-id']

    if not bc_account or not bc_player:
        m = re.search(r'<script>window\.GLOBAL_VARIABLES = JSON\.parse\("({.*?})"\);</script>', page_html)
        if m:
            global_vars = json.loads(m.group(1).replace('\\"', '\"'))
            # utils.write_file(global_vars, './debug/video.json')
            bc_account = global_vars['BRIGHTCOVE']['ACCOUNT_ID']
            bc_player = global_vars['BRIGHTCOVE']['PLAYER_ID']

    if not bc_account or not bc_player:
        logger.warning('unable to determine brightcove account/player data in ' + url)
        return ''

    player_url = 'https://players.brightcove.net/{}/{}_default/index.min.js'.format(bc_account, bc_player)
    player_js = utils.get_url_html(player_url)
    m = re.search(r'policyKey:"([^"]+)"', player_js)
    if not m:
        logger.warning('unable to find policyKey in ' + player_url)
        return ''

    args = {}
    args['data-account'] = bc_account
    args['data-video-id'] = video_id
    args['data-key'] = m.group(1)
    args['embed'] = True
    bc_item = brightcove.get_content(url, args, {}, False)
    return bc_item['content_html']


def add_super_quiz(url):
    split_url = urlsplit(url.replace('&amp;', '&'))
    query = parse_qs(split_url.query)
    if not query.get('configUrl'):
        logger.warning('unknown configUrl in ' + url)
        return ''
    config_json = utils.get_url_json(query['configUrl'][0])
    if not config_json:
        return ''
    quiz_html = '<h2>{}</h2>'.format(config_json['config']['name'])
    for i, data in enumerate(config_json['data']):
        q = re.sub(r'^<p>(.*)</p>$', r'\1', data['question'])
        quiz_html += '<details><summary>{}. {}</summary>{}</details>'.format(i + 1, q, data['answer'])
    return quiz_html


def add_imagebar_gallery(url):
    split_url = urlsplit(url.replace('&amp;', '&'))
    query = parse_qs(split_url.query)
    if not query.get('configUrl'):
        logger.warning('unknown configUrl in ' + url)
        return ''
    config_json = utils.get_url_json(query['configUrl'][0])
    if not config_json:
        return ''
    gallery_html = '<h3>{}</h3><table>'.format(config_json['config']['name'])
    for i, data in enumerate(config_json['data']):
        gallery_html += '<tr><td style="width:128px;"><img src="{}" style="width:128px;" /></td><td><a href="{}"><b>{}</b></a></td></tr>'.format(data['image'], data['buttonLink'], data['body'])
    gallery_html += '</table>'
    return gallery_html


def get_article_json(tld, article_id):
    api_url = 'https://api.{}.{}/api/content/v0/assets/{}'.format(tld.domain, tld.suffix, article_id)
    # print(api_url)
    return utils.get_url_json(api_url)


def get_article_url(article_json, domain, netloc):
    if article_json['urls'].get('canonical'):
        return 'https://{}{}'.format(netloc, article_json['urls']['canonical']['path'])
    elif article_json['urls'].get('published') and article_json['urls']['published'].get(domain):
        return 'https://{}{}'.format(netloc, article_json['urls']['published'][domain]['path'])
    elif article_json['urls'].get('external'):
        return article_json['urls']['external']
    else:
        logger.warning('unknown article url')
        return article_json['urls']['webslug']


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    tld = tldextract.extract(url)
    query = parse_qs(split_url.query)

    if 'embed' in args and 'photo-gallery' in url and query.get('configUrl'):
        config_json = utils.get_url_json(query['configUrl'][0])
        if config_json:
            item = {}
            item['content_html'] = '<h3>{}</h3><table>'.format(config_json['config']['name'])
            for data in config_json['data']:
                captions = []
                if data.get('caption'):
                    captions.append(data['caption'])
                if data.get('credit'):
                    captions.append(data['credit'])
                item['content_html'] += utils.add_image(data['image'], ' | '.join(captions))
            return item

    m = re.search(r'-(\w+?)(\.html)?$', split_url.path)
    if not m:
        logger.warning('unable to determine article id from ' + url)
        return None
    article_json = get_article_json(tld, m.group(1))
    if not article_json:
        return None
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['id']
    item['url'] = get_article_url(article_json, tld.domain, split_url.netloc)
    item['title'] = article_json['asset']['headlines']['headline']

    def format_date(matchobj):
        # convert nanoseconds to microseconds
        ms = int(int(matchobj.group(1)) / 1000)
        return '.{}Z'.format(str(ms).zfill(6))
    date = re.sub(r'\.(\d+)Z', format_date, article_json['dates']['published'])
    dt = datetime.fromisoformat(date.replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    date = re.sub(r'\.(\d+)Z', format_date, article_json['dates']['modified'])
    dt = datetime.fromisoformat(date.replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    if article_json.get('participants') and article_json['participants'].get('authors'):
        authors = []
        for it in article_json['participants']['authors']:
            authors.append(it['name'])
        if authors:
            item['author'] = {}
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    elif article_json['asset'].get('byline'):
        item['author'] = {"name": article_json['asset']['byline']}
    elif article_json.get('sources'):
        authors = []
        for it in article_json['sources']:
            authors.append(it['name'])
        if authors:
            item['author'] = {}
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = article_json['categories'].copy()
    if article_json.get('tags'):
        if article_json['tags'].get('primary'):
            item['tags'].append(article_json['tags']['primary']['name'])
        if article_json['tags'].get('secondary'):
            for it in article_json['tags']['secondary']:
                item['tags'].append(it['name'])

    item['summary'] = article_json['asset']['about']

    item['content_html'] = ''
    if article_json['asset'].get('intro'):
        item['content_html'] += '<p><em>{}</em></p>'.format(article_json['asset']['intro'])

    if article_json.get('featuredImages'):
        item['_image'] = resize_image(article_json['featuredImages']['landscape16x9']['data'])
        if article_json['asset'].get('bodyPlaceholders'):
            if article_json['assetType'] == 'article':
                if not next((it for it in article_json['asset']['bodyPlaceholders'].values() if (it['type'] == 'image' and it['data']['id'] == article_json['featuredImages']['landscape16x9']['data']['id'])), None):
                    item['content_html'] += add_image(article_json['featuredImages']['landscape16x9']['data'])

    if article_json['assetType'] == 'video':
        item['content_html'] += add_video(item['url'], '')
    elif article_json['assetType'] == 'gallery':
        for it in article_json['asset']['images']:
            item['content_html'] += add_image(it)
    else:
        # article_json['assetType'] == 'article'
        item['content_html'] += article_json['asset']['body']
        if article_json['asset'].get('bodyPlaceholders'):
            for key, val in article_json['asset']['bodyPlaceholders'].items():
                new_html = ''
                if val['type'] == 'image':
                    new_html = add_image(val['data'])
                elif val['type'] == 'video':
                    new_html = add_video(item['url'], val['data']['id'])
                elif val['type'] == 'twitter' or val['type'] == 'youtube':
                    new_html = utils.add_embed(val['data']['url'])
                elif val['type'] == 'omny':
                    new_html = utils.add_embed(val['data']['src'])
                elif val['type'] == 'iframe':
                    if 'nakedPointer.html' in val['data']['url']:
                        continue
                    elif '/super-quiz' in val['data']['url']:
                        new_html = add_super_quiz(val['data']['url'])
                    elif '/imagebar-gallery' in val['data']['url']:
                        new_html = add_imagebar_gallery(val['data']['url'])
                    elif '/podcast-pointer' in val['data']['url']:
                        continue
                    else:
                        new_html = utils.add_embed(val['data']['url'])
                elif val['type'] == 'quote':
                    if val['data']['type'] == 'pullquote':
                        new_html = utils.add_pullquote(val['data']['quote'], val['data']['quoteByline'])
                elif val['type'] == 'callout':
                    new_html = utils.add_blockquote('<h3>{}</h3>{}'.format(val['data']['title'], val['data']['body']))
                elif val['type'] == 'linkExternal':
                    new_html = '<a href="{}">{}</a>'.format(val['data']['url'], val['data']['text'])
                elif val['type'] == 'linkArticle':
                    link_json = get_article_json(tld, val['data']['id'])
                    if link_json:
                        new_html = '<a href="{}">{}</a>'.format(get_article_url(link_json, tld.domain, split_url.netloc), val['data']['text'])
                elif val['type'] == 'relatedStory':
                    continue
                    # link_json = get_article_json(tld, val['data']['id'])
                    # if link_json:
                    #     new_html = '<p><strong>Related Article:</strong> <a href="{}">{}</a></p>'.format(get_article_url(link_json, tld.domain, split_url.netloc), link_json['asset']['headlines']['headline'])
                if new_html:
                    item['content_html'] = re.sub(r'<x-placeholder id="{}"></x-placeholder>'.format(key), new_html, item['content_html'])
                else:
                    logger.warning('unhandled body placeholder type {} in {}'.format(val['type'], item['url']))

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><br/><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
