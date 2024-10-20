import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_next_data(url, site_json):
    # Getting next_data directly doesn't work reliably, especially for section pages
    next_data = None
    # split_url = urlsplit(url)
    # paths = list(filter(None, split_url.path.split('/')))
    # if paths[0] != 'hfm':
    #     if len(paths) == 0:
    #         path = '/index.json'
    #         query = ''
    #     else:
    #         path = split_url.path
    #         if path.endswith('/'):
    #             path = path[:-1]
    #         if len(paths) > 2 or paths[0] == 'tags':
    #             path += '/index.json'
    #         else:
    #             path += '.json'
    #         query = '?path=' + '&path='.join(paths)
    #     next_url = '{}://{}/_next/data/{}{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path, query)
    #     print(next_url)
    #     next_data = utils.get_url_json(next_url, retries=1)
    # if not next_data:
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('script', id='__NEXT_DATA__')
    if el:
        next_data = json.loads(el.string)
        # if paths[0] != 'hfm' and next_data['buildId'] != site_json['buildId']:
        #     logger.debug('updating {} buildId'.format(split_url.netloc))
        #     site_json['buildId'] = next_data['buildId']
        #     utils.update_sites(url, site_json)
        return next_data['props']
    return next_data


def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if next_data:
        utils.write_file(next_data, './debug/debug.json')

    article_json = next_data['pageProps']['articleStats']
    seo_data = next_data['pageProps']['seoData']
    ld_json = None
    for ld in next_data['pageProps']['jsonld']:
        if ld.get('@type') and ld['@type'] == 'NewsArticle':
            ld_json = ld
        elif ld.get('@graph'):
            for graph in ld['@graph']:
                if graph.get('@type') and graph['@type'] == 'NewsArticle':
                    ld_json = graph
                    break
        if ld_json:
            break

    item = {}
    item['id'] = article_json['articleID']
    item['url'] = article_json['cleanURL']
    item['title'] = article_json['headline']

    tz_loc = pytz.timezone(config.local_tz)
    dt_loc = datetime.fromtimestamp(article_json['originalDatePublication'] / 1000)
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt_loc = datetime.fromtimestamp(article_json['originalDateModified'] / 1000)
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_modified'] = dt.isoformat()

    if article_json.get('author'):
        item['authors'] = []
        for it in article_json['author']:
            item['authors'].append({"name": it})
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(article_json['author']))
        }

    item['tags'] = []
    if article_json.get('sectionKeyword'):
        item['tags'].append(article_json['sectionKeyword'])
    if article_json.get('keywords'):
        item['tags'] += article_json['keywords'].copy()
    if article_json.get('tags'):
        item['tags'] += article_json['tags'].copy()

    if ld_json and ld_json.get('image'):
        item['image'] = ld_json['image'][0]['url']
    else:
        image = next((it for it in seo_data['meta'] if it.get('property') == 'og:image'), None)
        if image:
            item['image'] = image['content']

    if article_json.get('description'):
        item['summary'] = article_json['description']

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    content_html = ''
    num_tags = 0
    for component in next_data['pageProps']['componentData']:
        if component['component'] == 'DigitalCoverMedia':
            if component['data']['dataProps']['containedProps'].get('subtitle'):
                content_html += '<p><em>' + component['data']['dataProps']['containedProps']['subtitle'] + '</em></p>'
            if component['data']['dataProps'].get('image'):
                img_src = component['data']['dataProps']['image']['src'] + '?tx=c_fill,w_1200'
                if 'image' not in item:
                    item['image'] = component['data']['dataProps']['image']['src']
                captions = []
                if component['data']['dataProps']['image'].get('caption'):
                    captions.append(component['data']['dataProps']['image']['caption'])
                if component['data']['dataProps']['image'].get('credit'):
                    captions.append(component['data']['dataProps']['image']['credit'])
                content_html += utils.add_image(img_src, ' | '.join(captions))
        elif component['component'] == 'ArticleHero':
            if component['data']['dataProps'].get('subtitle'):
                content_html += '<p><em>' + component['data']['dataProps']['subtitle'] + '</em></p>'
            if component['data']['dataProps'].get('image'):
                img_src = component['data']['dataProps']['image']['src'] + '?tx=c_fill,w_1200'
                if 'image' not in item:
                    item['image'] = component['data']['dataProps']['image']['src']
                captions = []
                if component['data']['dataProps']['image'].get('caption'):
                    captions.append(component['data']['dataProps']['image']['caption'])
                if component['data']['dataProps']['image'].get('credit'):
                    captions.append(component['data']['dataProps']['image']['credit'])
                content_html += utils.add_image(img_src, ' | '.join(captions))
        elif component['component'] == 'Article':
            for it in component['templateReplacers']:
                if it['body']:
                    content_html += it['obj']
        elif component['component'] == 'FactBox':
            new_html = '<div style="border:1px solid black; border-radius:10px; padding:0 1em 0 1em; margin:0 1em 0 1em;">'
            if component['data'].get('title'):
                new_html += '<h3>' + component['data']['title'] + '</h3>'
            # TODO: check if templateReplacers are duplicates
            new_html += component['templateReplacers'][0]['obj']
            new_html += '</div>'
            content_html = content_html.replace('{{{{{{{}}}}}}}'.format(component['configurationId']), new_html)
        elif component['component'] == 'Collapsiblebutton':
            new_html = '<div style="border:1px solid black; border-radius:10px; padding:0 1em 0 1em; margin:0 1em 0 1em;">'
            if component['data'].get('label'):
                new_html += '<h4>' + component['data']['label'] + '</h4>'
            for it in component['templateReplacers']:
                new_html += it['obj']
            new_html += '</div>'
            content_html = content_html.replace('{{{{{{{}}}}}}}'.format(component['configurationId']), new_html)
        elif component['component'] == 'ContentLink':
            new_html = ''
            if component['data'].get('dataUrl') and component['data'].get('innerHtml'):
                new_html = '<a href="{}">{}</a>'.format(component['data']['dataUrl'], component['data']['innerHtml'])
            content_html = content_html.replace('{{{{{{{}}}}}}}'.format(component['configurationId']), new_html)
        elif component['component'] == 'MediaImage':
            img_src = component['data']['image']['src'] + '?tx=c_fill,w_1200'
            captions = []
            if component['data']['image'].get('caption'):
                captions.append(component['data']['image']['caption'])
            if component['data']['image'].get('credit'):
                captions.append(component['data']['image']['credit'])
            new_html = utils.add_image(img_src, ' | '.join(captions))
            content_html = content_html.replace('{{{{{{{}}}}}}}'.format(component['configurationId']), new_html)
        elif component['component'] == 'SocialInstagram' or component['component'] == 'SocialTiktok':
            new_html = utils.add_embed(component['data']['dataUrl'])
            content_html = content_html.replace('{{{{{{{}}}}}}}'.format(component['configurationId']), new_html)
        elif component['component'] == 'JWPlayerVideo':
            new_html = utils.add_embed('https://content.jwplatform.com/players/{}.html'.format(component['data']['videoId']))
            content_html = content_html.replace('{{{{{{{}}}}}}}'.format(component['configurationId']), new_html)
        elif component['component'] == 'SpotifyPodcast':
            new_html = utils.add_embed(component['data']['playerSource'])
            content_html = content_html.replace('{{{{{{{}}}}}}}'.format(component['configurationId']), new_html)
        elif component['component'] == 'RelatedContent' or component['component'] == 'ContentTag':
            content_html = content_html.replace('{{{{{{{}}}}}}}'.format(component['configurationId']), '')
        elif component['component'] == 'GalleryListItem':
            new_html = ''
            if num_tags == 0:
                if next((it for it in next_data['pageProps']['componentData'] if it['component'] == 'ContentTag'), None):
                    num_tags = sum(1 for x in next_data['pageProps']['componentData'] if x['component'] == 'GalleryListItem')
                else:
                    num_tags = -1
            if num_tags > 0:
                new_html += '<p style="text-decoration:solid underline red 2px; margin-top:0;"><span class="contentTag" style="font-size:1.2em; font-weight:bold;">#</span><span>/{}</span></p>'.format(num_tags)
            img_src = component['data']['image']['src'] + '?tx=c_fill,w_1200'
            captions = []
            if component['data']['image'].get('caption'):
                captions.append(component['data']['image']['caption'])
            if component['data']['image'].get('credit'):
                captions.append(component['data']['image']['credit'])
            new_html += utils.add_image(img_src, ' | '.join(captions))
            if component['data'].get('title'):
                new_html += '<h4>' + component['data']['title'] + '</h4>'
            if component['data'].get('description'):
                new_html += component['data']['description']
            new_html += '<hr><div>&nbsp;</div>'
            content_html = content_html.replace('{{{{{{{}}}}}}}'.format(component['configurationId']), new_html)
        elif component['component'] == 'AffiliateProductArticle':
            new_html = ''
            if num_tags == 0:
                if next((it for it in next_data['pageProps']['componentData'] if it['component'] == 'ContentTag'), None):
                    num_tags = sum(1 for x in next_data['pageProps']['componentData'] if x['component'] == 'AffiliateProductArticle')
                else:
                    num_tags = -1
            if num_tags > 0:
                new_html += '<p style="text-decoration:solid underline red 2px; margin-top:0;"><span class="contentTag" style="font-size:1.2em; font-weight:bold;">#</span><span>/{}</span></p>'.format(num_tags)
            new_html += '<h3>' + component['data']['dataProps']['productName'] + '</h3>'
            if component['data']['dataProps'].get('image'):
                img_src = component['data']['dataProps']['image']['src'] + '?tx=c_fill,w_1200'
                captions = []
                if component['data']['dataProps']['image'].get('caption'):
                    captions.append(component['data']['dataProps']['image']['caption'])
                if component['data']['dataProps']['image'].get('credit'):
                    captions.append(component['data']['dataProps']['image']['credit'])
                new_html += utils.add_image(img_src, ' | '.join(captions))
            if component['data']['dataProps'].get('productDescription'):
                new_html += component['data']['dataProps']['productDescription']
            if component['data']['dataProps'].get('prosContent'):
                if new_html.endswith('</figure>'):
                    new_html += '<div>&nbsp;</div>'
                new_html += '<div style="border:1px solid black; border-radius:10px; padding:0 1em 0 1em; margin:0 1em 0 1em;">'
                if component['data']['dataProps'].get('pros'):
                    new_html += '<h4>' + component['data']['dataProps']['pros'] + '</h4>'
                new_html += component['data']['dataProps']['prosContent'] + '</div><div>&nbsp;</div>'
            if component['data']['dataProps'].get('consContent'):
                if new_html.endswith('</figure>'):
                    new_html += '<div>&nbsp;</div>'
                new_html += '<div style="border:1px solid black; border-radius:10px; padding:0 1em 0 1em; margin:0 1em 0 1em;">'
                if component['data']['dataProps'].get('cons'):
                    new_html += '<h4>' + component['data']['dataProps']['cons'] + '</h4>'
                new_html += component['data']['dataProps']['consContent'] + '</div><div>&nbsp;</div>'
            for it in component['data']['dataProps']['ctaButtons']:
                if it.get('productIdentifierSelectionText'):
                    btn_url = it['productIdentifierSelectionText']
                elif it.get('url'):
                    btn_url = it['url']
                elif it.get('squirrelProductIdentifier') == '__ASIN__':
                    btn_url = 'https://www.amazon.co.uk/dp/{}?th=1'.format(it['productIdentifierSelectionText'])
                if it.get('buttonText'):
                    caption = re.sub(r'^<p>|</p>$', '', it['buttonText'])
                elif it.get('squirrelProductIdentifier') == '__ASIN__':
                    caption = 'Buy on Amazon'
                else:
                    caption = 'Check price'
                new_html += utils.add_button(btn_url, caption)
            new_html += '<div>&nbsp;</div><hr><div>&nbsp;</div>'
            content_html = content_html.replace('{{{{{{{}}}}}}}'.format(component['configurationId']), new_html)
        elif component['component'] == 'ButtonWidgetArticles':
            new_html = utils.add_button(component['data']['link'], re.sub(r'^<p>|</p>$', '', component['data']['text']))
            content_html = content_html.replace('{{{{{{{}}}}}}}'.format(component['configurationId']), new_html)

    soup = BeautifulSoup(content_html, 'html.parser')
    for el in soup.find_all('widget'):
        el.unwrap()

    for el in soup.find_all(class_='fr-embedded'):
        el.unwrap()

    for el in soup.find_all('p', string=re.compile(r'SQUIRREL_ANCHOR_LIST')):
        el.decompose()

    for el in soup.select('p:has(> strong:-soup-contains("MORE:"))'):
        el.decompose()

    n = 1
    for el in soup.find_all('span', class_='contentTag'):
        el.string = str(n)
        n += 1

    for el in soup.find_all('p', id=True):
        el.attrs = {}

    for el in soup.find_all(attrs={"dir": "ltr"}):
        el.attrs = {}

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

    n = 0
    feed_items = []
    for component in next_data['pageProps']['componentData']:
        if component['component'] == 'SingleArticleTagIndexes':
            article_url = 'https://www.hellomagazine.com' + component['data']['content']['link']
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
        elif component['component'] == 'ArticleTaxonomyList':
            for article in component['data']['articles']:
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
        elif component['component'] == 'ContentGroupHomepages':
            for article in component['data']['props']['content']:
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

    feed = utils.init_jsonfeed(args)
    title = next((it for it in next_data['pageProps']['seoData']['metas'] if it.get('property') == 'og:title'), None)
    if title:
        feed['title'] = title['content']
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
