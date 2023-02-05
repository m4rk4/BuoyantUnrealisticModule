import re
from datetime import datetime
from urllib.parse import urlsplit, quote_plus

import utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def get_graphql_json(url):
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,de;q=0.8",
        "content-type": "application/json",
        "original-domain": "www.aljazeera.com",
        "sec-ch-ua": "\"Chromium\";v=\"104\", \" Not A;Brand\";v=\"99\", \"Microsoft Edge\";v=\"104\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "wp-site": "aje"
    }
    return utils.get_url_json(url, headers=headers)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if paths[0] == 'program':
        op_name = 'ArchipelagoSingleArticleQuery'
        post_type = 'episode'
    elif paths[0] == 'opinions':
        op_name = 'ArchipelagoSingleArticleQuery'
        post_type = 'opinion'
    elif paths[0] == 'gallery':
        op_name = 'ArchipelagoSingleGalleryQuery'
        post_type = 'gallery'
    else:
        op_name = 'ArchipelagoSingleArticleQuery'
        post_type = 'post'
    gql_url = 'https://www.aljazeera.com/graphql?wp-site=aje&operationName={}&variables=%7B%22name%22%3A%22{}%22%2C%22postType%22%3A%22{}%22%2C%22preview%22%3A%22%22%7D&extensions=%7B%7D'.format(op_name, quote_plus(paths[-1]), post_type)
    gql_json = get_graphql_json(gql_url)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/debug.json')

    article_json = gql_json['data']['article']
    item = {}
    item['id'] = article_json['id']
    item['url'] = 'https://www.aljazeera.com' + article_json['link']
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['date'] + '+00:00')
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['modified_gmt'] + '+00:00')
    item['date_modified'] = dt.isoformat()

    authors = []
    if article_json.get('author'):
        for it in article_json['author']:
            authors.append(it['name'])
    elif article_json.get('source'):
        for it in article_json['source']:
            authors.append(it['name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    if article_json.get('tags'):
        for it in article_json['tags']:
            item['tags'].append(it['title'])
    if article_json.get('categories'):
        for it in article_json['categories']:
            if it['name'] not in item['tags']:
                item['tags'].append(it['name'])
    if article_json.get('where'):
        for it in article_json['where']:
            if it['title'] not in item['tags']:
                item['tags'].append(it['title'])

    item['content_html'] = ''
    if article_json.get('excerpt'):
        item['summary'] = article_json['excerpt']
        item['content_html'] += '<p><em>{}</em></p>'.format(item['summary'])

    if article_json.get('featuredImage'):
        item['_image'] = 'https://www.aljazeera.com{}?w=1000x'.format(article_json['featuredImage']['sourceUrl'])

    if article_json.get('featuredYoutube'):
        item['content_html'] += utils.add_embed(article_json['featuredYoutube'])
    elif article_json.get('video') and article_json['video'].get('id'):
        item['content_html'] += utils.add_embed('https://players.brightcove.net/{}/{}_default/index.html?videoId={}'.format(article_json['video']['accountId'], article_json['video']['playerId'], article_json['video']['id']))
    elif article_json.get('featuredImage'):
        captions = []
        if article_json['featuredImage'].get('caption'):
            captions.append(article_json['featuredImage']['caption'])
        if article_json['featuredImage'].get('credit'):
            captions.append(article_json['featuredImage']['credit'])
        item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))

    item['content_html'] += wp_posts.format_content(article_json['content'], item)

    if article_json.get('galleryImages'):
        for image in article_json['galleryImages']:
            captions = []
            if image.get('caption'):
                captions.append(image['caption'])
            if image['image'].get('credit'):
                captions.append(image['image']['credit'])
            img_src = 'https://www.aljazeera.com{}?w=1000x'.format(image['image']['sourceUrl'])
            item['content_html'] += utils.add_image(img_src, ' | '.join(captions))

    item['content_html'] = re.sub(r'src="/', 'src="https://www.aljazeera.com/', item['content_html'])
    item['content_html'] = re.sub(r'</(figure|table)><(figure|table)', r'</\1><br/><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    if '/rss/' in args['url']:
        # https://www.aljazeera.com/xml/rss/all.xml
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    feed_title = ''
    articles = []
    split_url = urlsplit(args['url'])
    paths = list(filter(None, split_url.path[1:].split('/')))
    if paths[0] == 'author':
        gql_url = 'https://www.aljazeera.com/graphql?wp-site=aje&operationName=ArchipelagoAuthorPostsQuery&variables=%7B%22author_name%22%3A%22{}%22%2C%22quantity%22%3A10%2C%22offset%22%3A0%7D&extensions=%7B%7D'.format(paths[1])
        gql_json = get_graphql_json(gql_url)
        if gql_json:
            articles += gql_json['data']['articles'].copy()
        m = re.search(r'(.*)_\d+$', paths[1])
        if m:
            feed_title = 'Al Jazeera | {}'.format(m.group(1).replace('_', ' ').title())
    elif paths[0] == 'podcasts':
        if len(paths) > 1:
            gql_url = 'https://www.aljazeera.com/graphql?wp-site=aje&operationName=ArchipelagoSingleSeriesQuery&variables=%7B%22name%22%3A%22{}%22%2C%22postType%22%3A%22series%22%2C%22preview%22%3A%22%22%7D&extensions=%7B%7D'.format(paths[1])
        else:
            gql_url = 'https://www.aljazeera.com/graphql?wp-site=aje&operationName=ArchipelagoActivePodcastsQuery&variables=%7B%22offset%22%3A0%2C%22podcastType%22%3A%22featured%2Ccurrent%2Cother%2Ctv_show%22%2C%22quantity%22%3A50%7D&extensions=%7B%7D'
        gql_json = get_graphql_json(gql_url)
        if gql_json:
            articles += gql_json['data']['articles'].copy()
        feed_title = 'Al Jazeera | Podcasts'
    else:
        if paths[0] == 'tag':
            category_type = 'tags'
            name = paths[-1]
        elif paths[0] == 'where':
            category_type = 'where'
            name = paths[-1]
        else:
            category_type = 'categories'
            name = paths[-1]

        feed_title = 'Al Jazeera | {}'.format(name.replace('-', ' ').title())

        gql_url = 'https://www.aljazeera.com/graphql?wp-site=aje&operationName=ArchipelagoSectionQuery&variables=%7B%22name%22%3A%22{}%22%2C%22categoryType%22%3A%22{}%22%2C%22postTypes%22%3A%5B%22blog%22%2C%22episode%22%2C%22opinion%22%2C%22post%22%2C%22video%22%2C%22external-article%22%2C%22gallery%22%2C%22podcast%22%2C%22longform%22%2C%22liveblog%22%5D%2C%22quantity%22%3A4%7D&extensions=%7B%7D'.format(name, category_type)
        gql_json = get_graphql_json(gql_url)
        if gql_json:
            articles += gql_json['data']['articles'].copy()

        gql_url = 'https://www.aljazeera.com/graphql?wp-site=aje&operationName=ArchipelagoAjeSectionPostsQuery&variables=%7B%22category%22%3A%22{}%22%2C%22categoryType%22%3A%22{}%22%2C%22postTypes%22%3A%5B%22blog%22%2C%22episode%22%2C%22opinion%22%2C%22post%22%2C%22video%22%2C%22external-article%22%2C%22gallery%22%2C%22podcast%22%2C%22longform%22%2C%22liveblog%22%5D%2C%22quantity%22%3A10%2C%22offset%22%3A4%7D&extensions=%7B%7D'.format(name, category_type)
        gql_json = get_graphql_json(gql_url)
        if gql_json:
            articles += gql_json['data']['articles'].copy()

    if articles:
        n = 0
        feed_items = []
        for article in articles:
            url = 'https://www.aljazeera.com' + article['link']
            if save_debug:
                logger.debug('getting content for ' + url)
            item = get_content(url, args, site_json, save_debug)
            if item:
                if utils.filter_item(item, args) == True:
                    feed_items.append(item)
                    n += 1
                    if 'max' in args:
                        if n == int(args['max']):
                            break

    feed = utils.init_jsonfeed(args)
    if feed_title:
        feed['title'] = feed_title
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
