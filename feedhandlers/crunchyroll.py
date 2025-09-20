import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1200):
    split_url = urlsplit(img_src)
    if split_url.netloc != 'a.storyblock.com':
        return img_src
    m = re.search(r'/(\d+)x(\d+)/', split_url.path)
    if not m:
        return img_src
    w = int(m.group(1))
    h = int(m.group(2))
    if w <= width:
        return img_src
    return 'https://' + split_url.netloc + split_url.path + '/m/{}x0/filters:quality(95)format(webp)'.format(width)


def format_content(content):
    content_html = ''
    if content['type'] == 'text':
        start_tag = ''
        end_tag = ''
        if content.get('marks'):
            for it in content['marks']:
                if it['type'] == 'link':
                    start_tag += '<a href="' + it['attrs']['href'] + '"'
                    if it['attrs'].get('target'):
                        start_tag += ' target="' + it['attrs']['target'] + '"'
                    start_tag += '>'
                    end_tag = '</a>' + end_tag
                elif it['type'] == 'bold':
                    start_tag += '<strong>'
                    end_tag = '</strong>' + end_tag
                elif it['type'] == 'italic':
                    start_tag += '<em>'
                    end_tag = '</em>' + end_tag
                elif it['type'] == 'underline':
                    start_tag += '<span style="text-decoration:underline;">'
                    end_tag = '</span>' + end_tag
                elif it['type'] == 'styled':
                    if it['attrs']['class'] == 'textcolor-crorange':
                        start_tag += '<span style="color:#f47521;">'
                        end_tag = '</span>' + end_tag
                    elif it['attrs']['class'] == 'textcolor-crscooter':
                        start_tag += '<span style="color:#2abdbb;">'
                        end_tag = '</span>' + end_tag
                    elif it['attrs']['class'] == 'textcolor-honeygold':
                        start_tag += '<span style="color:#fabb18;">'
                        end_tag = '</span>' + end_tag
                    elif it['attrs']['class'] == 'textcolor-pomegranate':
                        start_tag += '<span style="color:#e13110;">'
                        end_tag = '</span>' + end_tag
                    elif it['attrs']['class'] == 'textcolor-tag':
                        continue
                    elif it['attrs']['class'] == 'textsize-small':
                        start_tag += '<small>'
                        end_tag = '</small>' + end_tag
                    else:
                        logger.warning('unhandled mark styled class ' + it['attrs']['class'])
                elif it['type'] == 'textStyle':
                    styles = []
                    for key, val in it['attrs'].items():
                        if val:
                            logger.debug('textStyle {}:{};'.format(key, val))
                            styles.append('{}:{};'.format(key, val))
                    if len(styles) > 0:
                        start_tag += '<span style="' + ' '.join(styles) + '">'
                        end_tag = '</span>' + end_tag
                else:
                    logger.warning('unhandled mark type ' + it['type'])
        content_html += start_tag + content['text'] + end_tag
    elif content['type'] == 'paragraph':
        if content.get('content'):
            content_html += '<p>'
            for it in content['content']:
                content_html += format_content(it)
            content_html += '</p>'
    elif content['type'] == 'heading':
        content_html += '<h{}>'.format(content['attrs']['level'])
        for it in content['content']:
            content_html += format_content(it)
        content_html += '</h{}>'.format(content['attrs']['level'])
    elif content['type'] == 'bullet_list':
        content_html += '<ul>'
        for it in content['content']:
            content_html += format_content(it)
        content_html += '</ul>'
    elif content['type'] == 'list_item':
        content_html += '<li>'
        for it in content['content']:
            content_html += format_content(it)
        content_html += '</li>'
    elif content['type'] == 'blockquote':
        content_html += '<blockquote style="' + config.blockquote_style + '">'
        for it in content['content']:
            content_html += format_content(it)
        content_html += '</blockquote>'
        if 'RELATED:' in content_html:
            return ''
    elif content['type'] == 'blok' and content['attrs'].get('body'):
        content_html += format_body(content['attrs']['body'])
    elif content['type'] == 'hard_break':
        content_html += '<br/>'
    elif content['type'] == 'horizontal_rule':
        content_html += '<hr style="margin:1em 0;"/>'
    else:
        logger.warning('unhandled content type ' + content['type'])
    return content_html


def format_body(body, rels=None, adv=None):
    body_html = ''
    for block in body:
        content_styles = []
        if block.get('content_alignment'):
            if block['content_alignment'] == 'textalign-center':
                content_styles.append('text-align:center;')
            else:
                logger.warning('unhandled content_alignment ' + block['content_alignment'])
        if block.get('content_color'):
            if block['content_color'] == 'textcolor-crorange':
                content_styles.append('color:#f47521;')
            elif block['content_color'] == 'textcolor-crscooter':
                content_styles.append('color:#2abdbb;')
            elif block['content_color'] == 'textcolor-honeygold':
                content_styles.append('color:#fabb18;')
            elif block['content_color'] == 'textcolor-pomegranate':
                content_styles.append('color:#e13110;')
            else:
                logger.warning('unhandled content_color ' + block['content_color'])
        if len(content_styles) > 0:
            body_html += '<div style="' + ' '.join(content_styles) + '">'
        if block['component'] == 'richtext' and block['content']['type'] == 'doc':
            for content in block['content']['content']:
                body_html += format_content(content)
        elif block['component'] == 'richtextindention' and block['content']['type'] == 'doc':
            body_html += '<div style="margin-left:25px;">'
            for content in block['content']['content']:
                body_html += format_content(content)
            body_html += '</div>'
        elif block['component'] == 'image':
            caption = ''
            if block.get('caption') and block['caption']['type'] == 'doc':
                for content in block['caption']['content']:
                    caption += format_content(content)
                caption = re.sub(r'^<p>|</p>$', '', caption)
            body_html += utils.add_image(resize_image(block['image']['filename']), caption)
        elif block['component'] == 'youtubeembed':
            m = re.search(r'src="([^"]+)', block['youtube'])
            if m:
                body_html += utils.add_embed(m.group(1))
        elif block['component'] == 'twitterembed':
            m = re.findall(r'href="([^"]+)', block['tweet'])
            if m:
                body_html += utils.add_embed(m[-1])
        elif block['component'] == 'htmlembed':
            soup = BeautifulSoup(block['htmlembed'], 'html.parser')
            el = soup.find_all('a', class_='btn')
            if el:
                for it in el:
                    body_html += utils.add_button(it['href'], it.decode_contents(), button_color='#ffbc1c')
            else:
                logger.warning('unhandled htmlembed body component')
        elif block['component'] == 'riddleembed':
            soup = BeautifulSoup(block['riddle'], 'html.parser')
            el = soup.find('iframe')
            if el:
                body_html += '<p><a href="' + el['src'] + '" target="_blank">'
                if el.get('title'):
                    body_html += el['title']
                else:
                    body_html += el['src']
                body_html += '</a></p>'
            else:
                logger.warning('unhandled riddleembed body component')
        elif block['component'] == 'columnswidget':
            body_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
            for it in block['items']:
                body_html += '<div style="margin:1em 0; flex:1; min-width:256px;">' + format_body([it], rels, adv) + '</div>'
            body_html += '</div>'
        elif block['component'] == 'article_banner_panel' and adv and adv.get('article_banner_panel'):
            if adv['article_banner_panel']['content'].get('link'):
                link = adv['article_banner_panel']['content']['link']['url']
            else:
                link = ''
            body_html += utils.add_image(resize_image(adv['article_banner_panel']['content']['desktop_image']['filename']), link=link)
        else:
            logger.warning('unhandled body component ' + block['component'])
        if len(content_styles) > 0:
            body_html += '</div>'
    return body_html


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    slug = '/'.join(paths[1:])
    api_url = 'https://cr-news-api-service.prd.crunchyrollsvc.com/v1/en-US/stories?slug=' + quote_plus(slug)
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    story_json = api_json['story']
    rels = api_json['rels']
    adv = api_json['adv']

    item = {}
    item['id'] = story_json['uuid']
    item['url'] = 'https://www.crunchroll.com/news/' + story_json['slug']
    item['title'] = story_json['content']['headline']

    dt = datetime.fromisoformat(story_json['content']['created_at'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(story_json['content']['updated_at'])
    item['date_modified'] = dt.isoformat()

    item['authors'] = []
    for it in story_json['content']['authors']:
        rel = next((x for x in rels if x['uuid'] == it), None)
        if rel:
            item['authors'].append({"name": rel['content']['name']})
    if len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }
    else:
        del item['authors']

    item['tags'] = []
    for it in rels:
        if 'content' in it and 'component' in it['content']:
            if it['content']['component'] == 'category':
                item['tags'].append(it['content']['title'])
            elif it['content']['component'] == 'articletype':
                item['tags'].append(it['content']['title'])
    if story_json.get('tag_list'):
        item['tags'] += story_json['tag_list'].copy()

    if story_json['content']['seo'].get('description'):
        item['summary'] = story_json['content']['seo']['description']

    item['content_html'] = ''
    if story_json['content'].get('lead'):
        item['content_html'] += '<p><em>' + story_json['content']['lead'] + '</em></p>'

    if story_json['content'].get('thumbnail'):
        item['image'] = resize_image(story_json['content']['thumbnail']['filename'])
        item['content_html'] += utils.add_image(item['image'])

    if story_json['content'].get('body'):
        item['content_html'] += format_body(story_json['content']['body'], rel, adv)

    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if len(paths) == 0 or paths[0] != 'news':
        logger.warning('unhandled feed url ' + url)
        return None
    if len(paths) == 1:
        slug = 'latest'
    else:
        slug = paths[1]
    api_url = 'https://cr-news-api-service.prd.crunchyrollsvc.com/v1/en-US/stories?slug=' + quote_plus(slug)
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    feed_title = api_json['story']['content']['seo']['title'] + ' | Crunchyroll News'
    categories = []
    for rel in api_json['rels']:
        if rel.get('content') and rel['content']['component'] == 'articletype':
            categories.append(rel['content']['title'])

    api_url = 'https://cr-news-api-service.prd.crunchyrollsvc.com/v1/en-US/stories/search?category=' + quote_plus(','.join(categories)) + '&page_size=10&page=1'
    logger.debug('getting stories from ' + api_url)
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/feed.json')

    n = 0
    feed_items = []
    for story in api_json['stories']:
        story_url = 'https://www.crunchyroll.com/news/' + story['slug']
        if save_debug:
            logger.debug('getting content for ' + story_url)
        item = get_content(story_url, args, site_json, save_debug)
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