import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


# Compatible sites
# https://scripps.com/our-brands/local-media/

def add_video(video):
    source = next((it for it in video['sources'] if it['type'] == 'mp4'), None)
    if source:
        video_type = 'video/mp4'
    else:
        source = next((it for it in video['sources'] if it['type'] == 'm3u8'), None)
        video_type = 'application/x-mpegURL'
    if video.get('caption'):
        caption = video['caption']
    else:
        caption = ''
    return utils.add_video(source['src'], video_type, video['thumbnailUrl'], caption)


def add_image(image):
    captions = []
    if image.get('caption'):
        captions.append(image['caption'])
    if image.get('credit'):
        captions.append(image['credit'])
    return utils.add_image(image['image']['src'], ' | '.join(captions))


def render_content(content):
    content_html = ''
    if isinstance(content, str):
        content_html += content
    elif content.get('_template'):
        if content['_template'] == '/core/article/RichTextArticleBody.hbs':
            for it in content['body']:
                content_html += render_content(it)
        elif content['_template'] == '/core/text/RichTextModule.hbs':
            for it in content['items']:
                content_html += render_content(it)
        elif content['_template'] == '/core/enhancement/Enhancement.hbs':
            for it in content['item']:
                content_html += render_content(it)
        elif content['_template'] == '/core/module/ModuleType.hbs':
            for it in content['content']:
                content_html += render_content(it)
        elif content['_template'] == '/core/link/Link.hbs':
            content_html += '<a href="{}">{}</a>'.format(content['href'], content['body'])
        elif content['_template'] == '/core/quote/Quote.hbs':
            content_html += utils.add_pullquote(content['quote'])
        elif content['_template'] == '/core/list/List.hbs':
            if content.get('title'):
                content_html += '<h4>{}</h4>'.format(content['title'])
            content_html += '<ul>'
            for it in content['items']:
                content_html += '<li>{}</li>'.format(render_content(it))
            content_html += '</ul>'
        elif content['_template'] == '/core/promo/Promo.hbs':
            if content.get('url') and content.get('title'):
                content_html += '<a href="{}">{}</a>'.format(content['url'], content['title'])
            else:
                logger.warning('unhandled Promo type ' + content['type'])
        elif content['_template'] == '/core/figure/Figure.hbs' or content['_template'] == '/core/image/Image.hbs':
            content_html += add_image(content)
        elif content['_template'] == '/core/video/VideoEnhancement.hbs':
            content_html += add_video(content['player'][0])
        elif content['_template'] == '/twitter/TweetUrl.hbs':
            soup = BeautifulSoup(content['externalContent'], 'html.parser')
            links = soup.find_all('a')
            content_html += utils.add_embed(links[-1]['href'])
        elif content['_template'] == '/twitter/TweetEmbed.hbs':
            soup = BeautifulSoup(content['embedCode'], 'html.parser')
            links = soup.find_all('a')
            content_html += utils.add_embed(links[-1]['href'])
        elif content['_template'] == '/facebook/FacebookEmbed.hbs' or content['_template'] == '/facebook/FacebookUrl.hbs':
            content_html += utils.add_embed(content['postUrl'])
        elif content['_template'] == '/core/iframe/IframeModule.hbs':
            if content['url'].startswith('//'):
                src = 'https:' + content['url']
            else:
                src = content['url']
            content_html += utils.add_embed(src)
        elif content['_template'] == '/core/htmlmodule/HtmlModule.hbs':
            if not re.search(r'download our apps|TOP STORIES', content['rawHtml'], flags=re.I):
                logger.warning('unknown rawHtml content')
        elif content['_template'] == '/customEmbed/EarlyElements.hbs' or content['_template'] == '/customEmbed/CustomEmbedModule.hbs':
            if not re.search(r'OUTBRAIN|Report a typo|ubscribe to', content['html'], flags=re.I):
                logger.warning('unknown customEmbed content')
        else:
            logger.warning('unhandled content template ' + content['_template'])
    elif content.get('items'):
        for it in content['items']:
            content_html += render_content(it)
    else:
        logger.warning('unhandled content block')
    return content_html


def get_content(url, args, save_debug=False):
    article_json = utils.get_url_json(utils.clean_url(url) + '?_renderer=json')
    if not article_json:
        return None
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    if article_json.get('meta'):
        meta_json = next((it for it in article_json['meta'] if it['_template'] == '/facebook/OpenGraphMeta.hbs'), None)
    else:
        meta_json = None

    item = {}
    item['id'] = article_json['contentId']
    if meta_json:
        item['url'] = meta_json['url']
    else:
        item['url'] = article_json['canonicalLink']
    item['title'] = article_json['headline']

    dt = datetime.fromisoformat(article_json['datePublishedISO'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    if article_json.get('dateModifiedISO'):
        dt = datetime.fromisoformat(article_json['dateModifiedISO'].replace('Z', '+00:00'))
        item['date_modified'] = dt.isoformat()
    elif article_json.get('updateDate'):
        date = re.sub('(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})([-+])(\d+)', r'\1-\2-\3T\4:\5:\6\7\8:00', article_json['updateDate'])
        dt = datetime.fromisoformat(date).astimezone(timezone.utc)
        item['date_modified'] = dt.isoformat()

    authors = []
    for it in article_json['people']:
        if it['type'] == 'author':
            authors.append(it['title'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    if meta_json:
        if meta_json['type'][0].get('tags'):
            item['tags'] = meta_json['type'][0]['tags'].copy()
    if article_json.get('keywords'):
        item['tags'] += article_json['keywords'].split(',')
    if not item.get('tags'):
        del item['tags']

    if article_json.get('description'):
        item['summary'] = article_json['description']
    elif meta_json and meta_json.get('description'):
        item['summary'] = meta_json['description']

    content_html = ''

    if article_json['_template'] == '/core/gallery/GalleryPage.hbs':
        item['_image'] = article_json['slides'][0]['mediaContent'][0]['image']['src']
        for content in article_json['galleryBody']:
            content_html += render_content(content)
        for slide in article_json['slides']:
            for content in slide['mediaContent']:
                content_html += render_content(content)
    else:
        if article_json.get('lead'):
            if article_json['lead'][0]['items'][0]['_template'] == '/core/image/Image.hbs':
                content_html += add_image(article_json['lead'][0]['items'][0])
                item['_image'] = article_json['lead'][0]['items'][0]['image']['src']
            elif article_json['lead'][0]['items'][0]['_template'] == '/wheel/WheelItemVideo.hbs':
                content_html += add_video(article_json['lead'][0]['items'][0])
                item['_image'] = article_json['lead'][0]['items'][0]['thumbnailUrl']

        for content in article_json['articleBody']:
            content_html += render_content(content)

        if article_json.get('lead') and len(article_json['lead'][0]['items']) > 1:
            content_html += '<h3>Additional media</h3>'
            for it in article_json['lead'][0]['items'][1:]:
                if it['_template'] == '/core/image/Image.hbs':
                    content_html += add_image(it)
                elif it['_template'] == '/wheel/WheelItemVideo.hbs':
                    content_html += add_video(it)

    soup = BeautifulSoup(content_html, 'html.parser')
    for el in soup.find_all(class_='twitter-tweet'):
        links = el.find_all('a')
        new_html = utils.add_embed(links[-1]['href'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        if el.parent and el.parent.name == 'p':
            el.parent.insert_after(new_el)
            el.parent.decompose()
        else:
            el.insert_after(new_el)
            el.decompose()

    for el in soup.find_all('iframe'):
        new_html = utils.add_embed(el['src'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        if el.parent and el.parent.name == 'p':
            el.parent.insert_after(new_el)
            el.parent.decompose()
        else:
            el.insert_after(new_el)
            el.decompose()

    for el in soup.find_all('script'):
        el.decompose()

    content_html = str(soup)
    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><br/><\2', content_html)
    return item


def get_feed(args, save_debug=False):
    if args['url'].endswith('rss'):
        return rss.get_feed(args, save_debug, get_content)

    page_json = utils.get_url_json(utils.clean_url(args['url']) + '?_renderer=json')
    if not page_json:
        return None
    if save_debug:
        utils.write_file(page_json, './debug/feed.json')

    articles = []
    def iter_module(module):
        nonlocal articles
        if module['_template'] == '/core/text/RichTextModule.hbs':
            return
        elif module['_template'] == '/module/Wrapper.hbs':
            for it in module['module']:
                iter_module(it)
        elif module['_template'] == '/core/list/List.hbs':
            for it in module['items']:
                iter_module(it)
        elif module['_template'] == '/core/promo/Promo.hbs':
            if module['type'] != 'external':
                if module['url'] not in articles:
                    articles.append(module['url'])
        else:
            logger.warning('unhandled module template ' + module['_template'])
    for it in page_json['main']:
        iter_module(it)

    n = 0
    feed_items = []
    for url in articles:
        if save_debug:
            logger.debug('getting content for ' + url)
        item = get_content(url, args, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed = utils.init_jsonfeed(args)
    feed['title'] = page_json['title']
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed