import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils

import logging

logger = logging.getLogger(__name__)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index'
    elif split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    path += '.json'
    next_url = '{}://{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
    if len(paths) == 3:
        next_url += '?league={}&slug={}'.format(paths[0], paths[2])
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        if page_html:
            soup = BeautifulSoup(page_html, 'lxml')
            el = soup.find('script', id='__NEXT_DATA__')
            if el:
                next_data = json.loads(el.string)
                if next_data['buildId'] != site_json['buildId']:
                    logger.debug('updating {} buildId'.format(split_url.netloc))
                    site_json['buildId'] = next_data['buildId']
                    utils.update_sites(url, site_json)
                return next_data['props']
    return next_data


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    gql_url = 'https://www.sportsline.com/ui-gateway/v1/graphql?query=%20query%7Barticle(slug:%22{}%22)%7Bid%20slug%20title%20body%20topic%20primaryTopicSlug%20articleType%20publishedAt%20updatedAt%20tags%7Bname%20slug%7DcanonicalUrl%20synopsis%20premiumContent,author%7Bid%20firstName%20lastName%20twitter%20byline%20clearHeadshotUrl%20nickName%7Dimages%7Bsrc%20height%20width%20caption%20name%7DrelatedArticles%7Bid%20slug%20title%20body%20topic%20articleType%20publishedAt%20premiumContent%20tags%7Bname%20slug%7DcanonicalUrl%20synopsis%20premiumContent,author%7Bid%20firstName%20lastName%20twitter%20byline%20clearHeadshotUrl%20nickName%20fullName%7Dimages%7Bsrc%20height%20width%20caption%20name%7D%7D%7D%7D'.format(paths[-1])
    gql_json = utils.get_url_json(gql_url)
    if gql_json:
        article_json = gql_json['data']['article']
    else:
        next_data = get_next_data(url, site_json)
        if not next_data:
            return None
        # utils.write_file(next_data, './debug/next.json')
        initial_state = json.loads(next_data['pageProps']['initialState'])
        # utils.write_file(initial_state, './debug/debug.json')
        article_json = initial_state['articleState']['article']

    if not article_json:
        return None
    return get_item(article_json, args, site_json, save_debug)


def get_item(article_json, args, site_json, save_debug):
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    if article_json.get('id'):
        item['id'] = article_json['id']
    elif article_json.get('contentId'):
        item['id'] = article_json['contentId']

    if article_json.get('canonicalUrl'):
        item['url'] = article_json['canonicalUrl']
    elif article_json.get('fullLink'):
        item['url'] = article_json['fullLink']
    elif article_json['articleType'] == 'NEWS':
        item['url'] = 'https://www.sportsline.com/{}/news/{}'.format(article_json['primaryTopicSlug'], article_json['slug'])
    elif article_json['articleType'] == 'ANALYSIS':
        item['url'] = 'https://www.sportsline.com/insiders/{}'.format(article_json['slug'])
    else:
        logger.warning('unhandled article type ' + article_json['articleType'])

    item['title'] = article_json['title']

    if article_json.get('publishedAt'):
        dt = datetime.fromisoformat(article_json['publishedAt'])
    elif article_json.get('publishDate'):
        dt = datetime.fromisoformat(article_json['publishDate'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    if article_json.get('updatedAt'):
        dt = datetime.fromisoformat(article_json['updatedAt'])
    elif article_json.get('modificationDate'):
        dt = datetime.fromisoformat(article_json['modificationDate'])
    item['date_modified'] = dt.isoformat()

    item['author'] = {"name": '{} {}'.format(article_json['author']['firstName'], article_json['author']['lastName'])}

    item['tags'] = []
    if article_json.get('topic'):
        item['tags'].append(article_json['topic'])

    item['content_html'] = ''
    if article_json.get('synopsis'):
        item['summary'] = article_json['synopsis']
        item['content_html'] += '<p><em>{}</em></p>'.format(article_json['synopsis'])

    image = None
    if article_json.get('heroImage'):
        image = article_json['heroImage']
    elif article_json.get('images'):
        image = article_json['images'][0]
    if image:
        item['_image'] = image['src']
        if image.get('caption'):
            caption = re.sub(r'<p>(.*?)</p>', r'\1', image['caption'])
        else:
            caption = ''
        item['content_html'] += utils.add_image(image['src'], caption)

    soup = BeautifulSoup(article_json['body'], 'html.parser')
    # Lede video seems to be promo
    if soup.contents[0].get('class') and 'embedVideo' in soup.contents[0]['class']:
        soup.contents[0].decompose()

    item['content_html'] += str(soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    # https://www.sportsline.com/all/news/
    # https://www.sportsline.com/ui-gateway/v1/graphql?query=%20query%7Barticles(tag:%22news%22,limit:10,offset:20)%7Barticles%7Bid%20slug%20title%20synopsis%20canonicalUrl%20tags%7Bname%7Dauthor%7Bid%20firstName%20lastName%20twitter%20byline%20nickName%7Dtopic%20primaryTopicSlug%20articleType%20publishedAt%7Dtotal%20offset%20limit%7D%7D&reqIdentifier=articleIndex
    # https://www.sportsline.com/nfl/news/
    # https://www.sportsline.com/ui-gateway/v1/graphql?query=%20query%7Barticles(league:%22nfl%22,tag:%22news%22,limit:10,offset:20)%7Barticles%7Bid%20slug%20title%20synopsis%20canonicalUrl%20tags%7Bname%7Dauthor%7Bid%20firstName%20lastName%20twitter%20byline%20nickName%7Dtopic%20primaryTopicSlug%20articleType%20publishedAt%7Dtotal%20offset%20limit%7D%7D&reqIdentifier=articleIndex
    # https://www.sportsline.com/nfl/articles/
    # https://www.sportsline.com/ui-gateway/v1/graphql?query=%20query%7Barticles(league:%22nfl%22,excludeTag:%22news%22,limit:10,offset:20)%7Barticles%7Bid%20slug%20title%20synopsis%20canonicalUrl%20tags%7Bname%7Dauthor%7Bid%20firstName%20lastName%20twitter%20byline%20nickName%7Dtopic%20primaryTopicSlug%20articleType%20publishedAt%7Dtotal%20offset%20limit%7D%7D&reqIdentifier=articleIndex
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))

    if len(paths) == 0:
        # default to https://www.sportsline.com/all/news/
        gql_url = 'https://www.sportsline.com/ui-gateway/v1/graphql?query=%20query%7Barticles(tag:%22news%22,limit:10,offset:0)%7Barticles%7Bid%20slug%20title%20body%20topic%20primaryTopicSlug%20articleType%20publishedAt%20updatedAt%20tags%7Bname%20slug%7DcanonicalUrl%20synopsis%20premiumContent,author%7Bid%20firstName%20lastName%20twitter%20byline%20clearHeadshotUrl%20nickName%7Dimages%7Bsrc%20height%20width%20caption%20name%7DrelatedArticles%7Bid%20slug%20title%20body%20topic%20articleType%20publishedAt%20premiumContent%20tags%7Bname%20slug%7DcanonicalUrl%20synopsis%20premiumContent,author%7Bid%20firstName%20lastName%20twitter%20byline%20clearHeadshotUrl%20nickName%20fullName%7Dimages%7Bsrc%20height%20width%20caption%20name%7D%7D%7D%7D%7D&reqIdentifier=articleIndex'
        feed_title = 'All News | SportsLine'
    elif 'news' in paths:
        # https://www.sportsline.com/nfl/news/
        if paths[0] == 'all':
            gql_url = 'https://www.sportsline.com/ui-gateway/v1/graphql?query=%20query%7Barticles(tag:%22news%22,limit:10,offset:0)%7Barticles%7Bid%20slug%20title%20body%20topic%20primaryTopicSlug%20articleType%20publishedAt%20updatedAt%20tags%7Bname%20slug%7DcanonicalUrl%20synopsis%20premiumContent,author%7Bid%20firstName%20lastName%20twitter%20byline%20clearHeadshotUrl%20nickName%7Dimages%7Bsrc%20height%20width%20caption%20name%7DrelatedArticles%7Bid%20slug%20title%20body%20topic%20articleType%20publishedAt%20premiumContent%20tags%7Bname%20slug%7DcanonicalUrl%20synopsis%20premiumContent,author%7Bid%20firstName%20lastName%20twitter%20byline%20clearHeadshotUrl%20nickName%20fullName%7Dimages%7Bsrc%20height%20width%20caption%20name%7D%7D%7D%7D%7D&reqIdentifier=articleIndex'.format(paths[0])
            feed_title = 'All News | SportsLine'.format(paths[0].upper())
        else:
            gql_url = 'https://www.sportsline.com/ui-gateway/v1/graphql?query=%20query%7Barticles(league:%22{}%22,tag:%22news%22,limit:10,offset:0)%7Barticles%7Bid%20slug%20title%20body%20topic%20primaryTopicSlug%20articleType%20publishedAt%20updatedAt%20tags%7Bname%20slug%7DcanonicalUrl%20synopsis%20premiumContent,author%7Bid%20firstName%20lastName%20twitter%20byline%20clearHeadshotUrl%20nickName%7Dimages%7Bsrc%20height%20width%20caption%20name%7DrelatedArticles%7Bid%20slug%20title%20body%20topic%20articleType%20publishedAt%20premiumContent%20tags%7Bname%20slug%7DcanonicalUrl%20synopsis%20premiumContent,author%7Bid%20firstName%20lastName%20twitter%20byline%20clearHeadshotUrl%20nickName%20fullName%7Dimages%7Bsrc%20height%20width%20caption%20name%7D%7D%7D%7D%7D&reqIdentifier=articleIndex'.format(paths[0])
            feed_title = '{} News | SportsLine'.format(paths[0].upper())
    elif 'articles' in paths:
        # https://www.sportsline.com/nfl/articles/
        if paths[0] == 'all':
            gql_url = 'https://www.sportsline.com/ui-gateway/v1/graphql?query=%20query%7Barticles(excludeTag:%22news%22,limit:10,offset:0)%7Barticles%7Bid%20slug%20title%20body%20topic%20primaryTopicSlug%20articleType%20publishedAt%20updatedAt%20tags%7Bname%20slug%7DcanonicalUrl%20synopsis%20premiumContent,author%7Bid%20firstName%20lastName%20twitter%20byline%20clearHeadshotUrl%20nickName%7Dimages%7Bsrc%20height%20width%20caption%20name%7DrelatedArticles%7Bid%20slug%20title%20body%20topic%20articleType%20publishedAt%20premiumContent%20tags%7Bname%20slug%7DcanonicalUrl%20synopsis%20premiumContent,author%7Bid%20firstName%20lastName%20twitter%20byline%20clearHeadshotUrl%20nickName%20fullName%7Dimages%7Bsrc%20height%20width%20caption%20name%7D%7D%7D%7D%7D&reqIdentifier=articleIndex'
            feed_title = 'All Articles | SportsLine'
        else:
            gql_url = 'https://www.sportsline.com/ui-gateway/v1/graphql?query=%20query%7Barticles(league:%22{}%22,excludeTag:%22news%22,limit:10,offset:0)%7Barticles%7Bid%20slug%20title%20body%20topic%20primaryTopicSlug%20articleType%20publishedAt%20updatedAt%20tags%7Bname%20slug%7DcanonicalUrl%20synopsis%20premiumContent,author%7Bid%20firstName%20lastName%20twitter%20byline%20clearHeadshotUrl%20nickName%7Dimages%7Bsrc%20height%20width%20caption%20name%7DrelatedArticles%7Bid%20slug%20title%20body%20topic%20articleType%20publishedAt%20premiumContent%20tags%7Bname%20slug%7DcanonicalUrl%20synopsis%20premiumContent,author%7Bid%20firstName%20lastName%20twitter%20byline%20clearHeadshotUrl%20nickName%20fullName%7Dimages%7Bsrc%20height%20width%20caption%20name%7D%7D%7D%7D%7D&reqIdentifier=articleIndex'.format(paths[0])
            feed_title = '{} Articles | SportsLine'.format(paths[0].upper())
    else:
        logger.warning('unhandled feed url ' + url)
        return None

    #print(gql_url)
    gql_json = utils.get_url_json(gql_url)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/feed.json')

    n = 0
    feed_items = []
    for article in gql_json['data']['articles']['articles']:
        if article.get('canonicalUrl'):
            article_url = article['canonicalUrl']
        elif article['articleType'] == 'NEWS':
            article_url = 'https://www.sportsline.com/{}/news/{}'.format(article['primaryTopicSlug'], article['slug'])
        elif article['articleType'] == 'ANALYSIS':
            article_url = 'https://www.sportsline.com/insiders/{}'.format(article['slug'])
        else:
            logger.warning('unhandled article type {} in {}'.format(article['articleType'], url))
            continue
        if save_debug:
            logger.debug('getting content for ' + article_url)
        item = get_item(article, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    feed['title'] = feed_title
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed