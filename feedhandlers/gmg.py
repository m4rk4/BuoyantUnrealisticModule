import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

import utils

import logging

logger = logging.getLogger(__name__)


def format_body_text(body_text, alt_link=''):
    soup = BeautifulSoup(body_text, 'html.parser')
    for el in soup.find_all(class_=['related-story-link-container', 'related-story-link']):
        el.decompose()
    for el in soup.select('p > strong:-soup-contains("RELATED:")'):
        el.find_parent('p').decompose()
    for el in soup.find_all(class_='wp-block-button'):
        if el.a.get('href'):
            link = utils.get_redirect_url(el.a['href'])
        elif alt_link:
            link = utils.get_redirect_url(alt_link)
        new_html = '<div><a href="{}"><span style="display:inline-block; min-width:180px; text-align: center; padding:0.5em; font-size:0.8em; color:white; background-color:#0072ed; border:1px solid #0072ed; border-radius:10px;">{}</span></a></div>'.format(link, el.a.decode_contents())
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()
    return str(soup)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    api_url = site_json['api_path'] + split_url.path
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    article_json = api_json['article'][0]
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['id']
    item['url'] = url
    item['title'] = article_json['headline']

    dt = datetime.fromisoformat(article_json['publishData']['date']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['publishData']['updated']).astimezone(timezone.utc)
    item['date_modified'] = dt.isoformat()

    item['author'] = {"name": article_json['author']['name']}

    if article_json.get('tags'):
        item['tags'] = article_json['tags'].copy()

    item['summary'] = article_json['seo']['metaDescription']

    item['content_html'] = ''
    if article_json.get('dek'):
        item['content_html'] += '<p><em>{}</em></p>'.format(article_json['dek'])

    if article_json.get('heroImage'):
        item['_image'] = article_json['heroImage']['imageSrcDesktop']
        if article_json['modules'][0]['type'] != 'recipe':
            captions = []
            if article_json['heroImage'].get('caption'):
                captions.append(article_json['heroImage']['caption'])
            if article_json['heroImage'].get('credit'):
                captions.append(article_json['heroImage']['credit'])
            item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))

    for module in article_json['modules']:
        if module['type'] == 'body-text':
            if module['data'].get('subHeader'):
                item['content_html'] += '<h3>{}</h3>'.format(module['data']['subHeader'])
            item['content_html'] += format_body_text(module['data']['bodyText'])
        elif module['type'] == 'sub-head':
            item['content_html'] += '<h3>{}</h3>'.format(module['data'])
        elif module['type'] == 'pull-quote':
            item['content_html'] += utils.add_pullquote(module['data']['bodyText'], module['data']['author'])
        elif module['type'] == 'large-image':
            captions = []
            if module['data'].get('caption'):
                captions.append(module['data']['caption'])
            if module['data'].get('credit'):
                captions.append(module['data']['credit'])
            desc = ''
            if module['data'].get('hed'):
                desc += '<h3>{}</h3>'.format(module['data']['hed'])
            # TODO: subhed
            if module['data'].get('bodyText'):
                desc += format_body_text(module['data']['bodyText'])
            item['content_html'] += utils.add_image(module['data']['imageSrcDesktop'], ' | '.join(captions), desc=desc)
        elif module['type'] == 'social-embed' or module['type'] == 'video-embed':
            if module['data'].get('hed'):
                item['content_html'] += '<h3>{}</h3>'.format(module['data']['hed'])
            if 'instagram-media' in module['data']['embed']:
                m = re.search(r'data-instgrm-permalink="([^"\?]+)', module['data']['embed'])
                item['content_html'] += utils.add_embed(m.group(1))
            elif 'twitter-tweet' in module['data']['embed']:
                m = re.findall(r'href="([^"]+)"', module['data']['embed'])
                item['content_html'] += utils.add_embed(m[-1])
            elif 'tiktok-embed' in module['data']['embed']:
                m = re.search(r'cite="([^"]+)"', module['data']['embed'])
                item['content_html'] += utils.add_embed(m.group(1))
            elif '<iframe' in module['data']['embed']:
                m = re.search(r'src="([^"]+)"', module['data']['embed'])
                item['content_html'] += utils.add_embed(m.group(1))
            else:
                logger.warning('unhandled social-embed module in ' + item['url'])
            if module['data'].get('subhed'):
                item['content_html'] += '<p><strong>{}</strong></h3>'.format(module['data']['subhed'])
            if module['data'].get('bodyText'):
                item['content_html'] += format_body_text(module['data']['bodyText'])
            if module['data'].get('buttonUrl'):
                item['content_html'] += '<div><a href="{}"><span style="display:inline-block; min-width:180px; text-align: center; padding:0.5em; font-size:0.8em; color:white; background-color:#0072ed; border:1px solid #0072ed; border-radius:10px;">{}</span></a></div><div>&nbsp;</div>'.format(utils.get_redirect_url(module['data']['buttonUrl']), module['data']['buttonText'])
        elif module['type'] == 'large-product':
            captions = []
            if module['data'].get('photoCredit'):
                captions.append(module['data']['photoCredit'])
            desc = ''
            if module['data'].get('title'):
                desc += '<div>&nbsp;</div><div><b>{}</b></div>'.format(module['data']['title'].upper())
            if module['data'].get('name'):
                desc += '<h3>{}</h3>'.format(module['data']['name'])
            if module['data'].get('bodyText'):
                desc += format_body_text(module['data']['bodyText'], module['data'].get('imageUrl'))
            item['content_html'] += utils.add_image(module['data']['imageSrcDesktop'], ' | '.join(captions), link=module['data'].get('imageUrl'), desc=desc)
        elif module['type'] == 'shoppable-grid':
            if module['data'].get('header'):
                item['content_html'] += '<h3>{}</h3>'.format(module['data']['header'])
            item['content_html'] += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
            for it in module['data']['products']:
                item['content_html'] += '<div style="flex:1; min-width:180px; max-width:256px; text-align:center; border:1px solid #B6DDE6;"><div><b>{}</b></div>'.format(it['name'])
                if it.get('productImage'):
                    item['content_html'] += '<div><img src="{}" style="width:100%;"/></div>'.format(it['productImage'])
                if it.get('price'):
                    item['content_html'] += '<div><small>${}</small></div>'.format(it['price'])
                if it.get('buttonUrl'):
                    item['content_html'] += '<div><a href="{}"><span style="display:inline-block; min-width:180px; text-align: center; padding:0.5em; font-size:0.8em; color:white; background-color:#0072ed; border:1px solid #0072ed; border-radius:10px;">{}</span></a></div><div>&nbsp;</div>'.format(utils.get_redirect_url(it['buttonUrl']), it['buttonText'])
                item['content_html'] += '</div>'
            item['content_html'] += '</div>'
        elif module['type'] == 'recipe':
            if module['data'].get('recipeTeaser'):
                item['content_html'] += '<p><em>{}</em></p>'.format(module['data']['recipeTeaser'])
            if module['data'].get('imageSrcDesktop'):
                item['content_html'] += utils.add_image(module['data']['imageSrcDesktop'], module['data'].get('imageCredit'))
            if module['data'].get('description'):
                item['content_html'] += format_body_text(module['data']['description'])
            if module['data'].get('byline'):
                item['content_html'] += '<table style="width:100%; table-layout:fixed; border:1px solid black;"><tr>'
                for it in module['data']['byline'].keys():
                    item['content_html'] += '<td style="text-align:center;"><b>{}</b></td>'.format(it.upper())
                if module['data'].get('servings'):
                    item['content_html'] += '<td style="text-align:center;"><b>SERVES</b></td>'
                item['content_html'] += '</tr><tr>'
                for it in module['data']['byline'].values():
                    item['content_html'] += '<td style="text-align:center;">{}</td>'.format(it)
                if module['data'].get('servings'):
                    item['content_html'] += '<td style="text-align:center;">{}</td>'.format(module['data']['servings'])
                item['content_html'] += '</tr></table><div>&nbsp;</div>'
            item['content_html'] += '<div style="font-size:1.2em; font-weight:bold; border-bottom:1px solid black;">Ingredients</div>' + module['data']['ingredients'] + '<div>&nbsp;</div>'
            item['content_html'] += '<div style="font-size:1.2em; font-weight:bold; border-bottom:1px solid black;">Directions</div>' + module['data']['directions'] + '<div>&nbsp;</div>'
            if module['data'].get('nutrition'):
                m = re.findall('<p>(.*?)</p>', module['data']['nutrition'])
                item['content_html'] += '<p>Nutrition Facts: ' + ' | '.join(m) + '</p>'
        elif module['type'] == 'related-stories':
            continue
        else:
            logger.warning('unhandled module type {} in {}'.format(module['type'], item['url']))

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    if not split_url.path or split_url.path == '/':
        api_url = site_json['api_path'] + '/home'
    else:
        api_url = site_json['api_path'] + split_url.path
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/feed.json')

    if '/author/' in url:
        articles = api_json['author']
    else:
        articles = api_json['articles']

    n = 0
    feed_items = []
    for article in articles:
        article_url = '{}://{}/{}'.format(split_url.scheme, split_url.netloc, article['url'])
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
    if api_json.get('landerMeta') and api_json['landerMeta'].get('title'):
        feed['title'] = api_json['landerMeta']['title']
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
