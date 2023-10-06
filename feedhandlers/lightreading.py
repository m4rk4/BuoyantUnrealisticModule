import re
import dateutil.parser
from bs4 import BeautifulSoup
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def render_content(contents):
    content_html = ''
    for content in contents:
        #print(content)
        if content['type'] == 'text':
            start_tag = ''
            end_tag = ''
            if content.get('marks'):
                for mark in content['marks']:
                    if mark['type'] == 'bold':
                        start_tag += '<b>'
                        end_tag = '</b>' + end_tag
                    elif mark['type'] == 'italic':
                        start_tag += '<i>'
                        end_tag = '</i>' + end_tag
                    elif mark['type'] == 'underline':
                        start_tag += '<u>'
                        end_tag = '</u>' + end_tag
                    elif mark['type'] == 'link':
                        start_tag += '<a href="{}">'.format(mark['attrs']['href'])
                        end_tag = '</a>' + end_tag
                    else:
                        logger.warning('unhandled mark type ' + mark['type'])
            content_html += start_tag + content['text'] + end_tag
        elif content['type'] == 'paragraph':
            if content.get('content'):
                content_html += '<p>' + render_content(content['content']) + '</p>'
        elif content['type'] == 'heading':
            if content.get('content'):
                content_html += '<h{0}>{1}</h{0}>'.format(content['attrs']['level'], render_content(content['content']))
        elif content['type'] == 'blockquote':
            if content.get('content'):
                content_html += utils.add_pullquote(render_content(content['content']))
        elif content['type'] == 'bulletList':
            if content.get('content'):
                content_html += '<ul>' + render_content(content['content']) + '</ul>'
        elif content['type'] == 'listItem':
            if content.get('content'):
                content_html += '<li>' + render_content(content['content']) + '</li>'
        elif content['type'] == 'hardBreak':
            content_html += '<br/>'
        elif content['type'] == 'image':
            img_src = ''
            captions = []
            title = ''
            desc = ''
            if content.get('content'):
                img_src = content['content']['src'] + '?width=1200&auto=webp&quality=70&format=jpg'
                if content['content'].get('title'):
                    title = '<h3>{}</h3>'.format(content['content']['title'])
            elif content.get('attrs'):
                img_src = content['attrs']['src'] + '?width=1200&auto=webp&quality=70&format=jpg'
                if content['attrs'].get('title'):
                    title = '<h3>{}</h3>'.format(content['attrs']['title'])
            if content.get('info'):
                if content['info'].get('caption'):
                    captions.append(content['info']['caption'])
                if content['info'].get('credit'):
                    captions.append(content['info']['credit'])
                if content['info'].get('description'):
                    desc = render_content(content['info']['description'])
            if img_src:
                content_html += utils.add_image(img_src, ' | '.join(captions), heading=title, desc=desc)
            else:
                logger.warning('unknown image src')
        elif content['type'] == 'figure':
            image = next((it for it in content['content'] if it['type'] == 'image'), None)
            if image:
                image_html = render_content([image])
                caption = next((it for it in content['content'] if it['type'] == 'text'), None)
                if caption:
                    image_html = image_html.replace('</figure>', '<figcaption><small>{}</small></figcaption></figure>'.format(caption['text']))
                content_html += image_html
            else:
                logger.warning('unhandle figure')
        elif content['type'] == 'iframe':
            content_html += utils.add_embed(content['attrs']['src'])
        elif content['type'] == 'ad' or content['type'] == 'relatedArticle':
            pass
        else:
            logger.warning('unhandled content type ' + content['type'])
    return content_html


def get_content(url, args, site_json, save_debug=False):
    api_url = '{}?_data=routes/$topic.$slug'.format(utils.clean_url(url))
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    item = {}
    item['id'] = api_json['template']['uid']
    item['url'] = api_json['seo']['canonicalUrl']
    item['title'] = api_json['template']['title']

    dt = dateutil.parser.parse(api_json['template']['publishedDate'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    # TODO: dateModified from schema

    if api_json['template'].get('contributors'):
        authors = []
        for it in api_json['template']['contributors']:
            authors.append(it['name'])
        if authors:
            item['author'] = {}
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    if api_json['template'].get('keywords'):
        for it in api_json['template']['keywords']:
            item['tags'].append(it['title'])
    if api_json['template'].get('topics'):
        for it in api_json['template']['topics']:
            if it['title'] not in item['tags']:
                item['tags'].append(it['title'])
    if not item.get('tags'):
        del item['tags']

    item['content_html'] = ''
    if api_json['template'].get('summary'):
        item['summary'] = api_json['template']['summary']
        item['content_html'] += '<p><em>{}</em></p>'.format(item['summary'])

    if api_json['template'].get('featuredImage'):
        item['_image'] = api_json['template']['featuredImage']['src'] + '?width=1200&auto=webp&quality=70&format=jpg'
        captions = []
        if api_json['template']['featuredImage'].get('caption'):
            captions.append(api_json['template']['featuredImage']['caption'])
        if api_json['template']['featuredImage'].get('creditTo'):
            captions.append(api_json['template']['featuredImage']['creditTo'])
        item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))

    if api_json['template'].get('atAGlance'):
        item['content_html'] += '<h2>At a Glance</h2><ul>'
        for it in api_json['template']['atAGlance']:
            item['content_html'] += '<li>{}</li>'.format(it)
        item['content_html'] += '</ul><hr/>'

    item['content_html'] += render_content(api_json['template']['bodyJson'])

    if api_json['template'].get('carousel'):
        item['content_html'] += '<h2>Slideshow</h2>'
        item['content_html'] += render_content(api_json['template']['carousel']['items'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    if 'rss.xml' in url:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if 'author' in paths:
        api_url = '{}?_data=routes/author.$slug'.format(utils.clean_url(url))
    else:
        api_url = '{}?_data=routes/$topic.$slug'.format(utils.clean_url(url))
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/feed.json')

    n = 0
    feed_items = []
    for article in api_json['template']['contents']:
        article_url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, article['articleUrl'])
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
    if api_json['seo'].get('metaTitle'):
        feed['title'] = api_json['seo']['metaTitle']
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
