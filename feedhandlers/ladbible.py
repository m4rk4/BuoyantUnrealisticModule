import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import jwplayer

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    query = parse_qs(split_url.query)
    if split_url.path == '/jw-iframe.html':
        return jwplayer.get_content('https://cdn.jwplayer.com/v2/media/{}?page_domain={}'.format(query['videoId'][0], split_url.netloc), args, {}, False)

    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "is-preview": "false",
        "pragma": "no-cache",
        "sec-ch-ua": "\"Microsoft Edge\";v=\"117\", \"Not;A=Brand\";v=\"8\", \"Chromium\";v=\"117\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36 Edg/117.0.2045.43"
    }
    gql_url = 'https://hive.ladbiblegroup.com/graphql?query=query%20GetArticle(%24channel%3A%20String%20%3D%20%22ladbible%22%2C%20%24staticLink%3A%20String!%2C%20%24useES%3A%20Boolean%20%3D%20false)%20%7B%0A%20%20article(channel%3A%20%24channel%2C%20staticLink%3A%20%24staticLink%2C%20useES%3A%20%24useES)%20%7B%0A%20%20%20%20...ArticlePage%0A%20%20%20%20__typename%0A%20%20%7D%0A%20%20adsConfig(channel%3A%20%24channel)%20%7B%0A%20%20%20%20refreshBlocks%0A%20%20%20%20jwPlayer%20%7B%0A%20%20%20%20%20%20click%0A%20%20%20%20%20%20auto%0A%20%20%20%20%20%20__typename%0A%20%20%20%20%7D%0A%20%20%20%20floatingAd%20%7B%0A%20%20%20%20%20%20enabled%0A%20%20%20%20%20%20timerEnabled%0A%20%20%20%20%20%20geos%20%7B%0A%20%20%20%20%20%20%20%20country%0A%20%20%20%20%20%20%20%20enabled%0A%20%20%20%20%20%20%20%20timerEnabled%0A%20%20%20%20%20%20%20%20__typename%0A%20%20%20%20%20%20%7D%0A%20%20%20%20%20%20__typename%0A%20%20%20%20%7D%0A%20%20%20%20__typename%0A%20%20%7D%0A%7D%0A%0Afragment%20ArticlePage%20on%20Article%20%7B%0A%20%20id%0A%20%20title%0A%20%20summary%0A%20%20bodyNodes%0A%20%20body%0A%20%20featuredImage%0A%20%20featuredImageInfo%20%7B%0A%20%20%20%20imageURL%0A%20%20%20%20credit%20%7B%0A%20%20%20%20%20%20text%0A%20%20%20%20%20%20link%0A%20%20%20%20%20%20__typename%0A%20%20%20%20%7D%0A%20%20%20%20__typename%0A%20%20%7D%0A%20%20featuredVideo%0A%20%20featuredVideoInfo%20%7B%0A%20%20%20%20id%0A%20%20%20%20title%0A%20%20%20%20description%0A%20%20%20%20provider%0A%20%20%20%20enabledAds%0A%20%20%20%20__typename%0A%20%20%7D%0A%20%20staticLink%0A%20%20publishedAt%0A%20%20publishedAtUTC%0A%20%20updatedAt%0A%20%20updatedAtUTC%0A%20%20categories%20%7B%0A%20%20%20%20name%0A%20%20%20%20slug%0A%20%20%20%20__typename%0A%20%20%7D%0A%20%20author%20%7B%0A%20%20%20%20name%0A%20%20%20%20slug%0A%20%20%20%20bio%0A%20%20%20%20avatar%0A%20%20%20%20twitterHandle%0A%20%20%20%20__typename%0A%20%20%7D%0A%20%20properties%20%7B%0A%20%20%20%20name%0A%20%20%20%20slug%0A%20%20%20%20__typename%0A%20%20%7D%0A%20%20types%20%7B%0A%20%20%20%20name%0A%20%20%20%20slug%0A%20%20%20%20__typename%0A%20%20%7D%0A%20%20tags%20%7B%0A%20%20%20%20name%0A%20%20%20%20slug%0A%20%20%20%20__typename%0A%20%20%7D%0A%20%20team%0A%20%20distributions%20%7B%0A%20%20%20%20name%0A%20%20%20%20slug%0A%20%20%20%20__typename%0A%20%20%7D%0A%20%20isSponsored%0A%20%20sponsor%20%7B%0A%20%20%20%20id%0A%20%20%20%20name%0A%20%20%20%20imageUrl%0A%20%20%20%20__typename%0A%20%20%7D%0A%20%20breaking%0A%20%20credits%20%7B%0A%20%20%20%20source%0A%20%20%20%20title%0A%20%20%20%20url%0A%20%20%20%20__typename%0A%20%20%7D%0A%20%20metaTitle%0A%20%20metaDescription%0A%20%20showRelatedVideo%0A%20%20showRelatedArticles%0A%20%20showAdverts%0A%20%20isLiveArticle%0A%20%20isLiveArticleActive%0A%20%20__typename%0A%7D%0A&operationName=GetArticle&variables=%7B%22channel%22%3A%22{}%22%2C%22useES%22%3Atrue%2C%22staticLink%22%3A%22{}%22%7D'.format(site_json['channel'], quote_plus(split_url.path[1:]))
    gql_json = utils.get_url_json(gql_url, headers=headers)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/debug.json')

    article_json = gql_json['data']['article']
    item = {}
    item['id'] = article_json['id']
    item['url'] = '{}://{}{}'.format(split_url.scheme, split_url.netloc, article_json['staticLink'])
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['publishedAtUTC'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['updatedAtUTC'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    item['author'] = {"name": article_json['author']['name']}

    item['tags'] = []
    for it in article_json['categories']:
        item['tags'].append(it['name'])
    for it in article_json['tags']:
        item['tags'].append(it['name'])

    item['content_html'] = ''
    if article_json.get('featuredVideo'):
        item['_image'] = article_json['featuredImage']
        #item['content_html'] += utils.add_video(article_json['featuredVideo'], 'video/mp4', article_json['featuredImage'], article_json['featuredVideoInfo'].get('title'))
        item['content_html'] += utils.add_embed('https://cdn.jwplayer.com/v2/media/' + article_json['featuredVideoInfo']['id'])
    elif article_json.get('featuredImage'):
        item['_image'] = article_json['featuredImage']
        item['content_html'] += utils.add_image(item['_image'], article_json['featuredImageInfo']['credit'].get('text'))

    if article_json.get('summary'):
        item['summary'] = article_json['summary']

    for node in article_json['bodyNodes']:
        if re.search(r'^<p[^>]*><img', node):
            m = re.search(r'<cite>(.+?)</cite>', node)
            if m:
                caption = m.group(1)
            else:
                caption = ''
            m = re.search(r'src="([^"]+)"', node)
            if m:
                item['content_html'] += utils.add_image(m.group(1), caption)
        elif re.search(r'^<p[^>]*><iframe', node):
            m = re.search(r'src="([^"]+)"', node)
            if m:
                item['content_html'] += utils.add_embed(m.group(1))
        elif re.search(r'class="social-embed"', node):
            content_html = ''
            if re.search(r'class="twitter-tweet"', node):
                m = re.findall(r'href="([^"]+)"', node)
                if m:
                    content_html = utils.add_embed(m[-1])
            elif re.search(r'class="instagram-media"', node):
                m = re.search(r'data-instgrm-permalink="([^"]+)"', node)
                if m:
                    content_html = utils.add_embed(m.group(1))
                else:
                    m = re.findall(r'href="(https://www\.instagram\.com/[^"]+)"', node)
                    if m:
                        content_html = utils.add_embed(m[-1])
            elif re.search(r'class="tiktok-embed"', node):
                m = re.search(r'cite="([^"]+)"', node)
                if m:
                    content_html = utils.add_embed(m.group(1))
            elif re.search(r'class="apester-media"', node):
                # Polls?
                # https://display.apester.com/interactions/597478a65ef522b21624dfb8/display?renderer=true&os=unknown&platform=desktop
                logger.debug('skipping apster-media embed in ' + item['url'])
                continue
            elif re.search(r'<iframe ', node):
                m = re.search(r'src="([^"]+)"', node)
                if m:
                    content_html = utils.add_embed(m.group(1))
            if content_html:
                item['content_html'] += content_html
            else:
                logger.warning('unhandled body node ' + node)
        else:
            item['content_html'] += node

    return item


def get_feed(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    m = re.search(r'window\.__APOLLO_STATE__ = ({.*?})</script>', page_html)
    if not m:
        return None
    apollo_state = json.loads(m.group(1))
    if save_debug:
        utils.write_file(apollo_state, './debug/feed.json')

    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    # gql_url = 'https://hive.ladbible.com/graphql?query=query%20GetArticles(%24channel%3A%20String%20%3D%20%22ladbible%22%2C%20%24meta%3A%20String%20%3D%20%22%22%2C%20%24category%3A%20String%20%3D%20%22%22%2C%20%24tag%3A%20String%20%3D%20%22%22%2C%20%24tags%3A%20%5BString%5D%2C%20%24rating%3A%20String%20%3D%20%22%22%2C%20%24limit%3A%20Int%20%3D%2010%2C%20%24offset%3A%20Int%20%3D%200%2C%20%24trending%3A%20Boolean%20%3D%20false%2C%20%24featured%3A%20Boolean%20%3D%20false%2C%20%24days%3A%20Int%20%3D%200%2C%20%24beforeDate%3A%20String%2C%20%24visibility%3A%20String%2C%20%24orderByPublished%3A%20Boolean%20%3D%20false%2C%20%24includeSponsored%3A%20Boolean%20%3D%20false%2C%20%24search%3A%20String%2C%20%24author%3A%20String%2C%20%24useES%3A%20Boolean%20%3D%20false%2C%20%24searchAfterId%3A%20String%2C%20%24excludeStaticLink%3A%20String%2C%20%24excludeMeta%3A%20String)%20%7B%0A%20%20articles(channel%3A%20%24channel%2C%20meta%3A%20%24meta%2C%20category%3A%20%24category%2C%20tag%3A%20%24tag%2C%20tags%3A%20%24tags%2C%20rating%3A%20%24rating%2C%20limit%3A%20%24limit%2C%20offset%3A%20%24offset%2C%20trending%3A%20%24trending%2C%20featured%3A%20%24featured%2C%20days%3A%20%24days%2C%20beforeDate%3A%20%24beforeDate%2C%20visibility%3A%20%24visibility%2C%20orderByPublished%3A%20%24orderByPublished%2C%20includeSponsored%3A%20%24includeSponsored%2C%20search%3A%20%24search%2C%20author%3A%20%24author%2C%20useES%3A%20%24useES%2C%20searchAfterId%3A%20%24searchAfterId%2C%20excludeStaticLink%3A%20%24excludeStaticLink%2C%20excludeMeta%3A%20%24excludeMeta)%20%7B%0A%20%20%20%20...ArticleList%0A%20%20%20%20__typename%0A%20%20%7D%0A%7D%0A%0Afragment%20ArticleList%20on%20Article%20%7B%0A%20%20id%0A%20%20staticLink%0A%20%20title%0A%20%20summary%0A%20%20publishedAt%0A%20%20publishedAtUTC%0A%20%20updatedAt%0A%20%20updatedAtUTC%0A%20%20author%20%7B%0A%20%20%20%20name%0A%20%20%20%20avatar%0A%20%20%20%20__typename%0A%20%20%7D%0A%20%20categories%20%7B%0A%20%20%20%20name%0A%20%20%20%20slug%0A%20%20%20%20__typename%0A%20%20%7D%0A%20%20tags%20%7B%0A%20%20%20%20name%0A%20%20%20%20slug%0A%20%20%20%20__typename%0A%20%20%7D%0A%20%20featuredImage%0A%20%20breaking%0A%20%20sortId%0A%20%20types%20%7B%0A%20%20%20%20name%0A%20%20%20%20slug%0A%20%20%20%20__typename%0A%20%20%7D%0A%20%20properties%20%7B%0A%20%20%20%20name%0A%20%20%20%20slug%0A%20%20%20%20__typename%0A%20%20%7D%0A%20%20showRelatedVideo%0A%20%20showRelatedArticles%0A%20%20showAdverts%0A%20%20isLiveArticle%0A%20%20isLiveArticleActive%0A%20%20__typename%0A%7D%0A&operationName=GetArticles&variables=%7B%22channel%22%3A%22{}%22%2C%22category%22%3A%22{}%22%2C%22limit%22%3A15%2C%22offset%22%3A0%2C%22trending%22%3Afalse%2C%22featured%22%3Afalse%2C%22orderByPublished%22%3Atrue%2C%22includeSponsored%22%3Afalse%2C%22useES%22%3Atrue%2C%22excludeMeta%22%3A%22%22%2C%22tags%22%3A%5B%5D%2C%22excludeStaticLink%22%3A%22%22%7D'.format(site_json['channel'], paths[0])
    # gql_json = utils.get_url_json(gql_url)
    # if not gql_json:
    #     return None
    # if save_debug:
    #     utils.write_file(gql_json, './debug/feed.json')

    n = 0
    feed_items = []
    for key, val in apollo_state.items():
        if key.startswith('Article:'):
            article_url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, val['staticLink'])
            if save_debug:
                logger.debug('getting content for ' + article_url)
            item = get_content(article_url, args, site_json, save_debug)
            if item:
                if utils.filter_item(item, args) == True:
                    feed_items.append(item)
                    n += 1
                    if 'max' in args:
                        if n == int(args['max']):
                            break

    feed = utils.init_jsonfeed(args)
    if len(paths) > 0:
        feed['title'] = '{} | {}'.format(paths[0].title(), split_url.netloc)
    else:
        feed['title'] = split_url.netloc
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed

