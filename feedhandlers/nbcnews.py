import json, re
import dateutil.parser
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import unquote_plus

import utils

import logging

logger = logging.getLogger(__name__)


def add_image(image, width=1200, height=800):
    captions = []
    if image.get('caption'):
        captions.append(image['caption'])
    if image.get('source') and image['source'].get('name'):
        captions.append(image['source']['name'])
    img_src = image['url']['primary'].replace('/upload/rockcms/', '/upload/w_{},h_{},c_fit/rockcms/'.format(width, height))
    return utils.add_image(img_src, ' | '.join(captions))


def add_video(video):
    video_src = ''
    video_asset = next((it for it in video['videoAssets'] if it['format'] == 'MPEG4'), None)
    if video_asset:
        page_html = utils.get_url_html(video_asset['publicUrl'])
        if not page_html:
            return ''
        soup = BeautifulSoup(page_html, 'html.parser')
        video_el = soup.find('video')
        if video_el:
            video_src = video_el['src']
            video_type = 'video/mp4'
    if not video_src:
        video_asset = next((it for it in video['videoAssets'] if it['format'] == 'M3U'), None)
        if video_asset:
            video_src = utils.get_redirect_url(video_asset['publicUrl'])
            video_type = 'application/x-mpegURL'
    poster = video['primaryImage']['url']['primary'].replace('/upload/rockcms/', '/upload/w_1200,h_800,c_fit/rockcms/')
    if video.get('headline') and video['headline'].get('primary'):
        caption = video['headline']['primary']
    elif video.get('description') and video['description'].get('primary'):
        caption = video['description']['primary']
    else:
        caption = ''
    return utils.add_video(video_src, video_type, poster, caption)


def render_contents(contents):
    content_html = ''
    for content in contents:
        if content['type'] == 'markup':
            if content['element'] == 'br' or content['element'] == 'hr':
                content_html += '<{}/>'.format(content['element'])
            else:
                content_html += '<{0}>{1}</{0}>'.format(content['element'], content['html'])
        elif content['type'] == 'embeddedImage':
            content_html += add_image(content['image'])
        elif content['type'] == 'embeddedVideo':
            content_html += add_video(content['video'])
        elif content['type'] == 'embeddedWidget':
            if content['widget']['name'] == 'IFRAMELY_EXTERNAL_EMBED':
                content_html += utils.add_embed(content['widget']['properties']['canonical-url'])
            elif content['widget']['name'] == 'youtubeplus':
                content_html += utils.add_embed('https://www.youtube.com/watch?v=' + content['widget']['properties']['youtube-id'])
            elif content['widget']['name'] == 'tweetplus_embed':
                soup = BeautifulSoup(unquote_plus(content['widget']['properties']['desktop']), 'html.parser')
                links = soup.find_all('a')
                content_html += utils.add_embed(links[-1]['href'])
            elif content['widget']['name'] == 'CUSTOM_EMBED' and content['widget']['properties']['embed']['type'] == 'BLOCKQUOTE':
                content_html += utils.add_pullquote(content['widget']['properties']['embed']['text'])
            elif content['widget']['name'] == 'CUSTOM_EMBED' and content['widget']['properties']['embed']['type'] == 'PULL_QUOTE':
                content_html += utils.add_pullquote(content['widget']['properties']['embed']['text'], content['widget']['properties']['embed'].get('attribution'))
            elif content['widget']['name'] == 'CUSTOM_EMBED' and content['widget']['properties']['embed']['type'] == 'SUMMARY_BOX':
                content_html += '<blockquote style="border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;"><h3>{}</h3><ul>'.format(content['widget']['properties']['embed']['headline'])
                for it in content['widget']['properties']['embed']['items']:
                    content_html += '<li>{}</li>'.format(it)
                content_html += '</ul></blockquote>'
            else:
                logger.warning('unhandled embeddedWidget ' + content['widget']['name'])
        elif content['type'] == 'embeddedTaxonomy':
            embed_json = utils.get_url_json('https://www.nbcnews.com/bentoapi/card/search?filters=type:card%20AND%20taxonomy:{}&size=150&page=1'.format(content['taxonomy']['path']))
            if embed_json:
                utils.write_file(embed_json, './debug/embed.json')
                for embed_item in embed_json['data']['search']['items']:
                    content_html += '<div>&nbsp;</div><hr/><div>&nbsp;</div><div style="font-size:1.2em; font-weight:bold;">{}</div><div style="font-size:0.9em;">'.format(embed_item['headline']['primary'])
                    if embed_item.get('authors'):
                        authors = []
                        for it in embed_item['authors']:
                            if it.get('person'):
                                authors.append(it['person']['name'])
                            elif it.get('name'):
                                authors.append(it['name'])
                        if authors:
                            content_html += 'By {}<br/>'.format(re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors)))
                    content_html += '{}</div><div>&nbsp;</div>'.format(utils.format_display_date(dateutil.parser.parse(embed_item['date']['publishedAt'])))
                    content_html += render_contents(embed_item['content']['markupAndEmbeds'])
        elif content['type'] == 'embeddedProduct':
            content_html += '<table><tr><td style="width:128px;"><img src="{}" style="width:100%;"/></td>'.format(content['product']['promotionalMedia'][0]['url']['primary'])
            link = utils.get_redirect_url(content['product']['offers'][0]['externalUrl'])
            content_html += '<td style="vertical-align:top;"><div style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></div><br/>'.format(link, content['product']['name'])
            for offer in content['product']['offers']:
                link = utils.get_redirect_url(offer['externalUrl'])
                prices = []
                for it in offer['prices']:
                    prices.append(float(it['price']))
                content_html += '<div><a href="{}">${:0.2f} at {}</a></div>'.format(link, min(prices), offer['seller']['name'])
            content_html += '</td></tr></table>'
        elif content['type'] == 'embeddedRecipe':
            content_html += '<table><tr><td style="width:128px;"><a href="{}"><img src="{}" style="width:100%;"/></a></td>'.format(content['recipe']['url']['primary'], content['recipe']['teaseImage']['url']['primary'])
            content_html += '<td style="vertical-align:top;"><div style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></div>'.format(content['recipe']['url']['primary'], content['recipe']['headline']['primary'])
            authors = []
            for it in content['recipe']['authors']:
                authors.append(it['name'])
            if authors:
                content_html += '<div>by {}</div>'.format(re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors)))
            content_html += '</td></tr></table>'
        else:
            logger.warning('unhandled content type ' + content['type'])
    return content_html


def get_next_data(url):
    page_html = utils.get_url_html(url)
    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('script', id='__NEXT_DATA__')
    if not el:
        logger.warning('unable to find __NEXT_DATA__ in ' + url)
        return None
    next_data = json.loads(el.string)
    return next_data


def get_content(url, args, site_json, save_debug=False):
    if 'dataviz.nbcnews.com' in url:
        # TODO: screenshot
        # https://dataviz.nbcnews.com/projects/20230818-precipitation-weather-map/?state=NY&hide=hed
        return None

    next_data = get_next_data(url)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/next.json')

    if next_data['props']['pageProps']['pageView'] == 'video':
        article_json = next_data['props']['initialState']['video']['current']
    elif next_data['props']['pageProps']['pageView'] == 'recipe':
        article_json = next_data['props']['initialState']['recipe']['current']
    else:
        article_json = next_data['props']['initialState']['article']['content'][0]
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['id']
    item['url'] = article_json['url']['canonical']
    item['title'] = article_json['headline']['primary']

    if article_json.get('date'):
        dt = datetime.fromisoformat(article_json['date']['publishedAt'].replace('Z', '+00:00'))
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        dt = datetime.fromisoformat(article_json['date']['modifiedAt'].replace('Z', '+00:00'))
        item['date_modified'] = dt.isoformat()
    else:
        dt = dateutil.parser.parse(article_json['datePublished'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        dt = dateutil.parser.parse(article_json['dateModified'])
        item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if article_json.get('authors'):
        item['authors'] = []
        for it in article_json['authors']:
            if it.get('person'):
                item['authors'].append({"name": it['person']['name']})
            elif it.get('name'):
                item['authors'].append({"name": it['name']})
        if len(item['authors']) > 0:
            item['author']= {
                "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
            }
    elif article_json.get('source'):
        item['author'] = {
            "name": article_json['source']['name'].title()
        }
        item['authors'] = []
        item['authors'].append(item['author'])
    elif article_json.get('publisher'):
        item['author'] = {
            "name": article_json['publisher']['name'].title()
        }
        item['authors'] = []
        item['authors'].append(item['author'])

    item['tags'] = []
    if article_json['taxonomy'].get('primarySection'):
        item['tags'].append(article_json['taxonomy']['primarySection']['name'])
    if article_json['taxonomy'].get('primaryTopic'):
        item['tags'].append(article_json['taxonomy']['primaryTopic']['name'])
    if article_json['taxonomy'].get('topics'):
        for it in article_json['taxonomy']['topics']:
            if it['name'] not in item['tags']:
                item['tags'].append(it['name'])
    if article_json['taxonomy'].get('additionalTerms'):
        for it in article_json['taxonomy']['additionalTerms']:
            if it['name'] not in item['tags']:
                item['tags'].append(it['name'])
    if not item.get('tags'):
        del item['tags']

    if article_json.get('teaseImage'):
        item['image'] = article_json['teaseImage']['url']['primary']
    elif article_json.get('socialImage'):
        item['image'] = article_json['socialImage']['url']['primary']

    if article_json.get('description'):
        item['summary'] = article_json['description']['primary']

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    item['content_html'] = ''
    if article_json.get('dek'):
        item['content_html'] += '<p><em>{}</em></p>'.format(article_json['dek'])

    if article_json.get('primaryMedia'):
        if article_json['primaryMedia']['type'] == 'embeddedImage':
            item['content_html'] += add_image(article_json['primaryMedia']['image'])
        elif article_json['primaryMedia']['type'] == 'embeddedVideo':
            item['content_html'] += add_video(article_json['primaryMedia']['video'])

    if article_json['type'] == 'video':
        item['content_html'] += add_video(article_json)
        if item.get('summary'):
            item['content_html'] += '<p>{}</p>'.format(item['summary'])

    if article_json.get('body'):
        item['content_html'] += render_contents(article_json['body'])

    if article_json['type'] == 'recipe':
        if article_json.get('aggregateRating'):
            item['content_html'] += '<p><b>Rating:</b> <span style="font-size:1.2em; font-weight:bold;">{}</span> / 5 <small>({})</small></p>'.format(article_json['aggregateRating']['ratingValue'], article_json['aggregateRating']['ratingCount'])
        if article_json.get('chefNotes'):
            item['content_html'] += render_contents(article_json['chefNotes'])
        if article_json.get('prepTime'):
            m = re.search(r'PT(\d+)M', article_json['prepTime'])
            if m:
                item['content_html'] += '<p><b>Prep Time:</b> {} mins</p>'.format(m.group(1))
            else:
                logger.warning('unknown prepTime in ' + item['url'])
        if article_json.get('cookTime'):
            m = re.search(r'PT(\d+)M', article_json['cookTime'])
            if m:
                item['content_html'] += '<p><b>Cook Time:</b> {} mins</p>'.format(m.group(1))
            else:
                logger.warning('unknown cookTime in ' + item['url'])
        if article_json.get('servingSize'):
            item['content_html'] += '<p><b>Servings:</b> {}</p>'.format(article_json['servingSize'])
        if article_json.get('yield'):
            item['content_html'] += '<p><b>Yields:</b> {}</p>'.format(article_json['yield'])
        item['content_html'] += '<h3><u>Ingredients</u></h3>'
        for ingredients in article_json['ingredients']:
            if ingredients['title']:
                item['content_html'] += '<h4>{}</h4>'.format(ingredients['title'])
            item['content_html'] += '<ul>'
            for it in ingredients['ingredients']:
                item['content_html'] += '<li>'
                if it.get('quantity'):
                    item['content_html'] += '<b>{}</b> '.format(it['quantity'])
                if it.get('measurementUnit'):
                    item['content_html'] += '{} '.format(it['measurementUnit'])
                item['content_html'] += '{}</li>'.format(it['name'])
            item['content_html'] += '</ul>'
        item['content_html'] += '<h3><u>Preparation</u></h3>' + render_contents(article_json['instructions'])

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    next_data = get_next_data(url)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    content_items = []
    if '/author/' in url:
        content_items = next_data['props']['pageProps']['person']['content']['items']
    else:
        for layout in next_data['props']['initialState']['front']['curation']['layouts']:
            for package in layout['packages']:
                content_items += package['items']

    n = 0
    feed_items = []
    for content in content_items:
        if 'deals.today.com' in content['computedValues']['url']:
            if save_debug:
                logger.debug('skipping content for ' + content['computedValues']['url'])
            continue
        if save_debug:
            logger.debug('getting content for ' + content['computedValues']['url'])
        item = get_content(content['computedValues']['url'], args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    if next_data['props']['pageProps'].get('category'):
        feed['title'] = '{} | On3.com'.format(next_data['pageProps']['category']['categoryName'])
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
