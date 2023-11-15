import pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_path, site_json, width=1080):
    return  '{}{}?w={}'.format(site_json['image_url'], img_path, width)


def add_image(image, site_json, width=1080):
    captions = []
    if image['entity'].get('caption'):
        captions.append(re.sub(r'</?p>', '', image['entity']['caption']))
    if image['entity'].get('credit'):
        captions.append(image['entity']['credit'])
    img_src = resize_image(image['entity']['mediaImage']['url'], site_json, width)
    return utils.add_image(img_src, ' | '.join(captions))


def render_content(content, site_json):
    content_html = ''
    if content['entity']['type'] == 'ParagraphContent':
        content_html += content['entity']['content']['value']

    elif content['entity']['type'] == 'ParagraphImageToolkitElement':
        content_html += add_image(content['entity']['image'], site_json)

    elif content['entity']['type'] == 'ParagraphImageGroup':
        for image in content['entity']['images']:
            content_html += add_image(image, site_json)

    elif content['entity']['type'] == 'ParagraphGalleryInlineElement':
        content_html += '<h3>Gallery: {}</h3>'.format(content['entity']['photoGallery']['entity']['title'])
        for image in content['entity']['photoGallery']['entity']['images']:
            content_html += add_image(image, site_json)

    elif content['entity']['type'] == 'ParagraphImmersiveLead':
        if content['entity'].get('immersiveImage'):
            content_html += add_image(content['entity']['immersiveImage'], site_json)
        else:
            logger.warning('unhandled ParagraphImmersiveLead')

    elif content['entity']['type'] == 'ParagraphVideoToolkit':
        if content['entity']['video']['entity'].get('image'):
            poster = resize_image(content['entity']['video']['entity']['image']['entity']['mediaImage']['url'], site_json)
        else:
            poster = ''
        caption = '<a href="https://www.nationalgeographic.co.uk{}"><strong>{}</strong></a>'.format(content['entity']['video']['entity']['url']['path'], content['entity']['video']['entity']['title'])
        if content['entity']['video']['entity'].get('promoSummary'):
            caption += '<br/>{}'.format(re.sub(r'</?p>', '', content['entity']['video']['entity']['promoSummary']['value']))
        video_src = ''
        if content['entity']['video']['entity']['video']['entity'].get('smilUrl'):
            smil = utils.get_url_html(content['entity']['video']['entity']['video']['entity']['smilUrl'])
            soup = BeautifulSoup(smil, 'html.parser')
            video_src = soup.video['src']
            video_type = soup.video['type']
        if video_src:
            content_html += utils.add_video(video_src, video_type, poster, caption)
        else:
            logger.warning('unhandled ParagraphVideoToolkit')

    elif content['entity']['type'] == 'ParagraphPullQuote':
        content_html += utils.add_pullquote(content['entity']['pullQuote'], content['entity']['source'])

    elif content['entity']['type'] == 'ParagraphInlinePromos':
        pass

    else:
        logger.warning('unhandled content type ' + content['entity']['type'])

    return content_html


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    if site_json.get('page_data_prefix') and split_url.path.startswith(site_json['page_data_prefix']):
        path = split_url.path[len(site_json['page_data_prefix']):]
    else:
        path = split_url.path
    if path.endswith('/'):
        path = path[:-1]
    api_url = '{}://{}{}/page-data{}/page-data.json'.format(split_url.scheme, split_url.netloc, site_json['page_data_prefix'], path)
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    article_json = api_json['result']['pageContext']['node']['data']['content']
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['id']
    item['url'] = 'https://{}{}'.format(split_url.netloc, article_json['url']['path'])
    item['title'] = article_json['title']

    tz_est = pytz.timezone('US/Eastern')
    dt_est = datetime.fromtimestamp(article_json['publishDate']['timestamp'])
    dt = tz_est.localize(dt_est).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    dt_est = datetime.fromtimestamp(article_json['dateOverride']['timestamp'])
    dt = tz_est.localize(dt_est).astimezone(pytz.utc)
    item['date_modified'] = dt.isoformat()

    authors = []
    for it in article_json['authors']:
        authors.append(it['entity']['name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if article_json.get('taxonomyTags'):
        item['tags'] = [it.strip() for it in article_json['taxonomyTags'].split(',')]
    elif article_json.get('metaTags'):
        item['tags'] = [it.strip() for it in article_json['metaTags']['keywords'].split(',')]
    else:
        item['tags'] = []
        item['tags'].append(article_json['primaryTaxonomy']['entity']['name'])
        for tax in ['taxEvents', 'taxGenres', 'taxSeries', 'taxPersons', 'taxSources', 'taxConcepts', 'taxSubjects', 'taxAudiences', 'taxLocations', 'taxOrganizations']:
            if article_json.get(tax):
                for it in article_json[tax]:
                    print(it)
                    item['tags'].append(it['entity']['name'])

    if article_json.get('promoImage'):
        item['_image'] = 'https://static.nationalgeographic.co.uk{}'.format(article_json['promoImage'][0]['entity']['mediaImage']['url'])

    item['content_html'] = ''
    if article_json.get('subHeadline'):
        item['summary'] = article_json['subHeadline']
        item['content_html'] += '<p><em>{}</em></p>'.format(article_json['subHeadline'])

    if article_json.get('immersiveLead'):
        item['content_html'] += render_content(article_json['immersiveLead'], site_json)
    elif article_json.get('image'):
        item['content_html'] += add_image(article_json['image'], site_json)

    if article_json.get('mainContent'):
        for content in article_json['mainContent']:
            item['content_html'] += render_content(content, site_json)

    if article_json.get('images'):
        for content in article_json['images']:
            item['content_html'] += add_image(content, site_json)

    item['content_html'] = re.sub(r'</figure><(figure|table)', r'</figure><div>&nbsp;</div><\1', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(args['url'])
    if len(split_url.path) <= 1:
        path = '/index'
    elif site_json.get('page_data_prefix') and split_url.path.startswith(site_json['page_data_prefix']):
        path = split_url.path[len(site_json['page_data_prefix']):]
    else:
        path = split_url.path
    if path.endswith('/'):
        path = path[:-1]
    api_url = '{}://{}{}/page-data{}/page-data.json'.format(split_url.scheme, split_url.netloc, site_json['page_data_prefix'], path)
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None

    page_json = api_json['result']['pageContext']['node']['data']['content']
    if save_debug:
        utils.write_file(page_json, './debug/feed.json')

    articles = []
    for content in page_json['mainContent']:
        if content['entity']['type'] == 'ParagraphContentPackage1':
            articles.append(content['entity']['cardGlobalLarge']['entity']['url']['path'])
        else:
            logger.warning('unhandled feed content type ' + content['entity']['type'])

    for content in page_json['termContent']['data']['featured']:
        articles.append(content['props']['data']['url'])

    for content in page_json['termContent']['data']['pagination']:
        for it in content:
            articles.append(it[1])

    feed = utils.init_jsonfeed(args)
    feed['title'] = page_json['title']
    feed_items = []
    for path in articles:
        url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, path)
        if save_debug:
            logger.debug('getting content for ' + url)
        item = get_content(url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)

    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed

