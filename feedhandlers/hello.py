import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_next_data(url, site_json):
    next_data = None
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if paths[0] != 'hfm':
        if len(paths) == 0:
            path = '/index.json'
            query = ''
        else:
            path = split_url.path
            if path.endswith('/'):
                path = path[:-1]
            if len(paths) > 2 or paths[0] == 'tags':
                path += '/index.json'
            else:
                path += '.json'
            query = '?path=' + '&path='.join(paths)

        next_url = '{}://{}/_next/data/{}{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path, query)
        next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('script', id='__NEXT_DATA__')
        if el:
            next_data = json.loads(el.string)
            if paths[0] != 'hfm' and next_data['buildId'] != site_json['buildId']:
                site_json['buildId'] = next_data['buildId']
                utils.update_sites(url, site_json)
            next_data = next_data['props']
    return next_data


def add_widgets(widgets, content_html):
    list_item = -1
    for widget in widgets:
        widget_html = ''
        if widget['type'] == 'content/link':
            #print(widget['id'])
            if widget.get('innerHtml'):
                widget_html += '<a href="{}">{}</a>'.format(widget['dataUrl'], widget['innerHtml'])
        elif widget['type'] == 'media/image':
            captions = []
            if widget.get('caption'):
                captions.append(widget['caption'])
            if widget.get('credit') and widget['credit'] != '[]':
                captions.append(re.sub(r'^\["(.*)"\]$', r'\1', widget['credit']))
            img_src = 'https://images.hellomagazine.com/horizon/original_aspect_ratio/{}.jpg?tx=c_fill,w_1200'.format(
                widget['image']['id'])
            widget_html += utils.add_image(img_src, ' | '.join(captions))
        elif widget['type'] == 'social/instagram' or widget['type'] == 'social/twitter':
            widget_html += utils.add_embed(widget['dataUrl'])
        elif widget['type'] == 'video/youtube':
            widget_html += utils.add_embed('https://www.youtube.com/watch?v=' + widget['dataId'])
        elif widget['type'] == 'widget/content-panel':
            if widget.get('identifier') and widget['identifier'] == 'listitem':
                if list_item < 0:
                    if next((w for w in widgets if (w['type'] == 'widget/content-tag' and w['identifier'] == 'listitem-group-numbered')), None):
                        list_item = 1
                    else:
                        list_item = 0
                if list_item > 0:
                    # Widgets aren't in order, so we have to do the numbers at the end
                    widget_html += '<div class="list_item" style="text-decoration:underline; text-decoration-thickness:3px;"></div>'
            widget_html += add_widgets(widget['embeddedItems'], widget['template'])
        elif widget['type'] == 'widget/content-tag' and (widget['identifier'] == 'listitem-group-numbered' or widget['identifier'] == 'listitem-group-unnumbered'):
            pass
        elif widget['type'] == 'widget/system':
            if widget['configuration'].get('articles') or widget['configuration'].get('affiliateProduct') or widget['configuration'].get('fact'):
                pass
            elif widget['configuration'].get('videoId'):
                widget_html += utils.add_embed('https://cdn.jwplayer.com/v2/media/{}'.format(widget['configuration']['videoId']))
            elif widget['configuration'].get('link') and widget['configuration'].get('text'):
                if widget['configuration'].get('image'):
                    img_src = 'https://images.hellomagazine.com/horizon/original_aspect_ratio/{}.jpg?tx=c_fill,w_1200'.format(widget['configuration']['image'])
                    widget_html += utils.add_image(img_src) + '<div>&nbsp;</div>'
                text = BeautifulSoup(widget['configuration']['text'], 'html.parser').get_text()
                widget_html += '<div style="text-align:center; padding:1em;"><span style="background-color:black; padding:0.5em;"><a href="{}" style="color:white;">{}</a></span></div>'.format(utils.get_redirect_url(widget['configuration']['link']), text)
            else:
                logger.warning('unhandled widget/system ' + widget['id'])
                continue
        elif widget['type'] == 'AffiliateProduct':
            widget_html += '<div style="width:90%; margin-left:auto; margin-right:auto; border:1px solid black; padding:8px;">'
            if widget['configuration'].get('index'):
                widget_html += '<div><span style="font-size:2em; font-weight:bold;">{}</span>/{}</div>'.format(widget['configuration']['index'], widget['configuration']['total'])
            widget_html += '<h3>{}</h3>'.format(widget['configuration']['product']['productTitle'])
            if widget['configuration']['product'].get('productImage'):
                widget_html += utils.add_image(widget['configuration']['product']['productImage']['src'])
            widget_html += '<h3 style="text-align:center;">{}</h3>'.format(widget['configuration']['product']['productName'])
            if widget['configuration']['product'].get('productDescription'):
                widget_html += widget['configuration']['product']['productDescription']
            for button in widget['configuration']['product']['ctaButtons']:
                widget_html += '<div style="text-align:center; padding:1em;"><span style="background-color:black; padding:0.5em;"><a href="{}" style="color:white;">{}</a></span></div>'.format(utils.get_redirect_url(button['url']), button['label'])
            widget_html += '</div><div>&nbsp;</div>'
        else:
            logger.warning('unhandled widget ' + widget['id'])
            continue
        content_html = re.sub(r'{{{{{{{}}}}}}}'.format(widget['id']), widget_html, content_html)
    return content_html

def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if next_data:
        utils.write_file(next_data, './debug/debug.json')

    article_json = next_data['pageProps']['articleStats']
    seo_data = next_data['pageProps']['seoData']
    item = {}
    item['id'] = article_json['articleID']
    item['url'] = article_json['cleanURL']
    item['title'] = seo_data['title']

    dt = datetime.fromtimestamp(article_json['originalDatePublication'] / 1000).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromtimestamp(article_json['originalDateModified'] / 1000).replace(tzinfo=timezone.utc)
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(article_json['author']))

    item['tags'] = []
    if article_json.get('sectionKeyword'):
        item['tags'].append(article_json['sectionKeyword'])
    if article_json.get('keywords'):
        item['tags'] += article_json['keywords'].copy()
    if article_json.get('tags'):
        item['tags'] += article_json['tags'].copy()

    content_html = ''
    for component in next_data['pageProps']['componentData']:
        if component['component'] == 'ArticleHero':
            item['title'] = component['data']['dataProps']['title']
            if component['data']['dataProps'].get('subtitle'):
                content_html += '<p><em>{}</em></p>'.format(BeautifulSoup(component['data']['dataProps']['subtitle'], 'html.parser').get_text())
            if component['data']['dataProps'].get('image'):
                item['_image'] = component['data']['dataProps']['image']['src'] + '?tx=c_fill,w_1200'
                captions = []
                if component['data']['dataProps']['image'].get('caption'):
                    captions.append(component['data']['dataProps']['image']['caption'])
                if component['data']['dataProps']['image'].get('credit'):
                    captions.append(component['data']['dataProps']['image']['credit'])
                content_html += utils.add_image(item['_image'], ' | '.join(captions))
        elif component['component'] == 'Article':
            for it in component['templateReplacers']:
                if it['body']:
                    content_html += it['obj']
            if component.get('unresolvedWidgets'):
                content_html = add_widgets(component['unresolvedWidgets'], content_html)
        elif (component['component'] == 'AffiliateProductListsArticle' or component['component'] == 'FactBox'):
            template = ''
            for it in component['templateReplacers']:
                template += it['obj']
            component_html = add_widgets(component['unresolvedWidgets'], template)
            content_html = re.sub(r'{{{{{{{}}}}}}}'.format(component['configurationId']), component_html, content_html)

    soup = BeautifulSoup(content_html, 'html.parser')
    for el in soup.find_all(class_='fr-embedded'):
        el.unwrap()
    for el in soup.find_all('widget'):
        if el.get('data-type') and el['data-type'] == 'FactBox':
            el.name = 'blockquote'
            el.attrs = {}
            el['style'] = 'border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;'
    list_items = soup.find_all(class_='list_item')
    list_total = len(list_items)
    for i, el in enumerate(list_items):
        new_html = '<span style="font-size:2em; font-weight:bold;">{}</span>/{}'.format(i+1, list_total)
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.append(new_el)
    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', str(soup))
    return item


def get_feed(url, args, site_json, save_debug=False):
    if url.endswith('.xml'):
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    articles = []
    for component in next_data['pageProps']['componentData']:
        if component['component'] == 'SingleArticleTagIndexes':
            articles.append(component['data']['content'])
        elif component['component'] == 'ArticleTaxonomyList':
            articles += component['data']['articles']

    n = 0
    feed_items = []
    feed = utils.init_jsonfeed(args)
    for article in articles:
        article_url = 'https://www.hellomagazine.com' + article['link']
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
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
