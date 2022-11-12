import json, re, tldextract
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    split_url = urlsplit(img_src)
    return 'https://{}{}?fm=jpg&fl=progressive&w={}&fit=pad'.format(split_url.netloc, split_url.path, width)


def add_image(image):
    captions = []
    if image.get('caption'):
        if image['caption'].get('plaintext'):
            captions.append(image['caption']['plaintext'])
        else:
            caption = re.sub(r'^<em>(.*)</em>$', r'\1', image['caption']['html'])
            caption = caption.replace('</em>', '<EM>').replace('<em>', '</EM>')
            captions.append(caption)
    if image.get('credit'):
        if image['credit'].get('plaintext'):
            captions.append(image['credit']['plaintext'])
        else:
            captions.append(image['credit']['html'])
    if image.get('url'):
        img_src = image['url']
    elif image.get('variantUrl'):
        img_src = image['variantUrl']
    elif image.get('main'):
        img_src = image['main']
    else:
        logger.warning('unknown image src')
        img_src = ''
    return utils.add_image(img_src, ' | '.join(captions))


def add_video_embed(uuid):
    embed_url = 'https://volume.vox-cdn.com/embed/' + uuid
    embed_html = utils.get_url_html(embed_url)
    if not embed_html:
        return ''
    m = re.search(r'var setup = ({.*});\n', embed_html)
    if not m:
        logger.warning('unable to load embed setup data from ' + embed_url)
        return ''
    embed_json = json.loads(m.group(1))
    #utils.write_file(embed_json, './debug/video.json')
    if embed_json['preferred_player_type'] == 'youtube':
        return utils.add_embed('https://www.youtube.com/embed/' + embed_json['player_setup']['video']['youtube_id'])
    elif embed_json['preferred_player_type'] == 'chorus':
        if embed_json['embed_assets']['chorus'].get('mp4_url'):
            return utils.add_video(embed_json['embed_assets']['chorus']['mp4_url'], 'video/mp4', embed_json['embed_assets']['chorus']['poster_url'], embed_json['embed_assets']['chorus']['title'])
        else:
            return utils.add_video(embed_json['embed_assets']['chorus']['hls_url'], 'application/x-mpegURL', embed_json['embed_assets']['chorus']['poster_url'], embed_json['embed_assets']['chorus']['title'])
    logger.warning('unhandled embed player type {} in {}'.format(embed_json['preferred_player_type'], embed_url))


def get_next_data(url):
    page_html = utils.get_url_html(url)
    soup = BeautifulSoup(page_html, 'html.parser')
    el = soup.find('script', id='__NEXT_DATA__')
    if not el:
        return None
    return json.loads(el.string)

def render_body_component(component):
    content_html = ''
    if component['__typename'] == 'EntryBodyParagraph':
        if component.get('dropcap') == True:
            if component['contents']['html'][0] == '<':
                content_html += re.sub(r'^(<[^>]+>)(\w)(.*)', r'<p>\1<span style="float:left; font-size:4em; line-height:0.8em;">\2</span>\3</p><span style="clear:left;"></span>', component['contents']['html'])
            else:
                content_html += '<p><span style="float:left; font-size:4em; line-height:0.8em;">{}</span>{}</p><span style="clear:left;"></span>'.format(component['contents']['html'][0], component['contents']['html'][1:])
        else:
            content_html += '<p>{}</p>'.format(component['contents']['html'])

    elif component['__typename'] == 'EntryBodyHeading':
        content_html += '<h{0}>{1}</h{0}>'.format(component['level'], component['contents']['html'])

    elif component['__typename'] == 'EntryBodyList':
        for it in component['items']:
            content_html += '<li>{}</li>'.format(it['line']['html'])
        if component.get('ordered'):
            content_html = '<ol>' + content_html + '</ol>'
        else:
            content_html = '<ul>' + content_html + '</ul>'

    elif component['__typename'] == 'EntryBodyImage':
        content_html += add_image(component['image'])

    elif component['__typename'] == 'EntryImage':
        content_html += add_image(component)

    elif component['__typename'] == 'EntryBodyImageGroup':
        if component.get('ImageGroupTwoUp'):
            for it in component['ImageGroupTwoUp']:
                content_html += add_image(it)
        else:
            logger.warning('unhandled EntryBodyImageGroup')

    elif component['__typename'] == 'EntryBodyImageComparison':
        content_html += '<figure style="margin:0; padding:0;"><img loading="lazy" style="width:50%;" src="{}" /><img loading="lazy" style="width:50%;" src="{}" /><figcaption><small>{}</small></figcaption></figure>'.format(component['imageComparison']['firstImage']['asset']['url'], component['imageComparison']['secondImage']['asset']['url'], component['imageComparison']['caption']['html'])

    elif component['__typename'] == 'EntryBodyGallery':
        content_html += '<h3>{}</h3>'.format(component['gallery']['title'])
        for it in component['gallery']['images']:
            content_html += add_image(it)

    elif component['__typename'] == 'EntryLeadImage':
        content_html += add_image(component['standard'])

    elif component['__typename'] == 'EntryBodyVideo' or component['__typename'] == 'EntryLeadVideo':
        content_html += add_video_embed(component['video']['uuid'])

    elif component['__typename'] == 'EntryEmbed' or component['__typename'] == 'EntryBodyEmbed' or component['__typename'] == 'EntryLeadEmbed':
        if component['__typename'] == 'EntryEmbed':
            embed = component
        else:
            embed = component['embed']
        soup = BeautifulSoup(embed['embedHtml'], 'html.parser')
        if embed.get('provider') and embed['provider']['name'] == 'Twitter':
            links = soup.find_all('a')
            content_html += utils.add_embed(links[-1]['href'])
        elif embed.get('provider') and embed['provider']['name'] == 'TikTok':
            content_html += utils.add_embed(soup.blockquote['cite'])
        elif soup.iframe:
            content_html += utils.add_embed(soup.iframe['src'])
        else:
            logger.warning('unhandled ' + component['__typename'])

    elif component['__typename'] == 'EntryBodyHTML':
        soup = BeautifulSoup(component['rawHtml'], 'html.parser')
        if soup.iframe and soup.iframe['src'] == 'https://www.platformer.news/embed':
            pass
        elif soup.find(id='toc-main'):
            pass
        elif soup.iframe:
            content_html += utils.add_embed(soup.iframe['src'])
        else:
            logger.warning('unhandled EntryBodyHTML')

    elif component['__typename'] == 'EntryBodyBlockquote':
        quote = ''
        for it in component['paragraphs']:
            quote += '<p>{}</p>'.format(it['contents']['html'])
        content_html = utils.add_blockquote(quote)

    elif component['__typename'] == 'EntryBodyPullquote':
        content_html += utils.add_pullquote(component['quote']['html'])

    elif component['__typename'] == 'EntryBodyHorizontalRule':
        content_html += '<hr/>'

    elif component['__typename'] == 'EntryExternalLink':
        content_html += '<p><a href="{}">{}</a> [{}]</p>'.format(component['url'], component['title'], component['source'])

    elif component['__typename'] == 'EntryRelatedEntry':
        content_html += '<table><tr>'
        if component['entry'].get('leadComponent'):
            if component['entry']['leadComponent']['__typename'] == 'EntryLeadImage':
                img_src = component['entry']['leadComponent']['square']['variantUrl']
            elif component['entry']['leadComponent']['__typename'] == 'EntryLeadVideo':
                img_src = component['entry']['leadComponent']['video']['square']['variantUrl']
            content_html += '<td style="width:128px;"><img src="{}" style="width:100%;" /></td>'.format(img_src)
        dt = datetime.fromisoformat(component['entry']['publishDate'].replace('Z', '+00:00'))
        content_html += '<td><a href="{}"><b>{}</b></a><br/>by {}, {}</td></tr></table>'.format(component['entry']['url'], component['entry']['title'], component['entry']['author']['fullName'], utils.format_display_date(dt, False))

    elif component['__typename'] == 'EntryBodyTable':
        if component['table'].get('title'):
            content_html += '<h3>{}</h3>'.format(component['table']['title'])
        content_html += '<table style="width:100%; border:1px solid black;">'
        if component['table'].get('columns'):
            content_html += '<tr>'
            for it in component['table']['columns']:
                content_html += '<th>{}</th>'.format(it)
            content_html += '</tr>'
        for i, row in enumerate(component['table']['rows']):
            if i%2 == 0:
                style = 'text-align:center; background-color:lightgray;'
            else:
                style = 'text-align:center;'
            content_html += '<tr>'
            for it in row:
                content_html += '<td style="{}">{}</td>'.format(style, it)
            content_html += '</tr>'
        content_html += '</table>'

    elif component['__typename'] == 'EntryBodyScorecard':
        if component.get('scorecard'):
            content_html += '<table style="width:90%; padding:8px; margin-left:auto; margin-right:auto; border:1px solid black;"><tr><td colspan="2"><img src="{}" style="width:100%;"/></td></tr>'.format(component['scorecard']['product']['imageUrl'])
            if component['scorecard']['product'].get('productBrand'):
                product_name = '{} {}'.format(component['scorecard']['product']['productBrand']['name'], component['scorecard']['product']['name'])
            else:
                product_name = component['scorecard']['product']['name']
            content_html += '<tr><td colspan="2" style="text-align:center; padding-bottom:8px; border-bottom:1px solid black;"><span style="font-size:2em; font-weight:bold;">{}</span><br/><span style="font-size:1.2em; font-weight:bold;">{}</span></td></tr>'.format(component['scorecard']['score'], product_name)

            if component['scorecard']['pros'][0].get('items'):
                content_html += '<tr><td style="width:50%; vertical-align:top; padding:8px; border-right:1px solid black; border-bottom:1px solid black;"><b>The Good</b><ul>'
                for it in component['scorecard']['pros'][0]['items']:
                    content_html += '<li>{}</li>'.format(it['line']['html'])
                content_html += '</ul></td><td style="width:50%; vertical-align:top; padding:8px; border-bottom:1px solid black;"><b>The Bad</b><ul>'
                for it in component['scorecard']['cons'][0]['items']:
                    content_html += '<li>{}</li>'.format(it['line']['html'])
                content_html += '</ul></td></tr>'

            if component['scorecard']['product'].get('retailers'):
                content_html += '<tr>'
                if len(component['scorecard']['product']['retailers']) > 1:
                    for i in range(2):
                        it = component['scorecard']['product']['retailers'][i]
                        if it.get('salePrice'):
                            price = float(it['salePrice'])
                        else:
                            price = float(it['price'])
                        content_html += '<td style="width:50%; padding-top:8px;"><div style="width:250px; padding:10px; margin:auto; background-color:red; text-align:center; color:white;"><a href="{}" style="color:white; text-decoration:none;">${:.2f} at {}</a></div></td>'.format(utils.get_redirect_url(it['url']), price, it['storeName'])
                else:
                    it = component['scorecard']['product']['retailers'][0]
                    if it.get('salePrice'):
                        price = float(it['salePrice'])
                    else:
                        price = float(it['price'])
                    content_html += '<td colspan="2" style="padding-top:8px;"><div style="width:250px; padding:10px; margin:auto; background-color:red; text-align:center; color:white;"><a href="{}" style="color:white; text-decoration:none;">${:.2f} at {}</a></div></td>'.format(utils.get_redirect_url(it['url']), price, it['storeName'])
                content_html += '</tr>'
            content_html += '</table>'

    elif component['__typename'] == 'EntryBodyProduct':
        content_html += '<table style="width:100%;"><tr><td style="width:50%;"><img src="{}" style="width:100%;" /></td><td style="vertical-align:top;"><span style="font-size:1.2em; font-weight:bold;">{}</span><br/>Retail price ${:.2f}<br/><br/>{}</td></tr><tr>'.format(component['product']['image']['variantUrl'], component['product']['title'], float(component['product']['retailers'][0]['price']), component['product']['description']['html'])
        if len(component['product']['retailers']) > 1:
            for i in range(2):
                it = component['product']['retailers'][i]
                if it.get('salePrice'):
                    price = float(it['salePrice'])
                else:
                    price = float(it['price'])
                content_html += '<td style="width:50%; padding-top:8px;"><div style="width:250px; padding:10px; margin:auto; background-color:red; text-align:center; color:white;"><a href="{}" style="color:white; text-decoration:none;">${:.2f} at {}</a></div></td>'.format(utils.get_redirect_url(it['url']), price, it['name'])
        else:
            it = component['product']['retailers'][0]
            if it.get('salePrice'):
                price = float(it['salePrice'])
            else:
                price = float(it['price'])
            content_html += '<td colspan="2" style="padding-top:8px;"><div style="width:250px; padding:10px; margin:auto; background-color:red; text-align:center; color:white;"><a href="{}" style="color:white; text-decoration:none;">${:.2f} at {}</a></div></td>'.format(utils.get_redirect_url(it['url']), price, it['name'])
        content_html += '</tr></table>'

    elif component['__typename'] == 'EntryBodySidebar':
        for it in component['sidebar']['body']:
            content_html += render_body_component(it)
        content_html = utils.add_blockquote(content_html)

    elif component['__typename'] == 'EntryBodyActionbox':
        if component['url'] == 'http://bit.ly/2JzR5Ud':
            pass
        else:
            logger.warning('unhandled EntryBodyActionbox')

    elif component['__typename'] == 'EntryBodyRelatedList' or component['__typename'] == 'EntryBodyNewsletter':
        pass

    else:
        logger.warning('unhandled body component type ' + component['__typename'])

    return content_html


def get_item(entry_json, args, save_debug):
    if save_debug:
        utils.write_file(entry_json, './debug/debug.json')

    item = {}

    if entry_json.get('_id'):
        item['id'] = entry_json['_id']
    else:
        split_url = urlsplit(entry_json['shortLink'])
        paths = list(filter(None, split_url.path.split('/')))
        item['id'] = paths[-1]

    item['url'] = entry_json['url']

    if entry_json['type'] == 'QUICK_POST':
        item['title'] = 'Quick Post: ' + entry_json['title']
    else:
        item['title'] = entry_json['title']

    dt = datetime.fromisoformat(entry_json['originalPublishDate'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(entry_json['publishDate'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    item['author'] = {"name": entry_json['author']['fullName']}

    item['tags'] = []
    if entry_json.get('communityGroups'):
        for it in entry_json['communityGroups']:
            if it['name'] != 'Front Page':
                item['tags'].append(it['name'])
    if not item.get('tags'):
        del item['tags']

    if entry_json.get('leadImage'):
        item['_image'] = entry_json['leadImage']['variantUrl']
    elif entry_json.get('promoImage'):
        item['_image'] = entry_json['promoImage']['variantUrl']
    elif entry_json.get('socialImage'):
        item['_image'] = entry_json['socialImage']['variantUrl']

    if entry_json.get('seoDescription'):
        item['summary'] = entry_json['seoDescription']['plaintext']
    elif entry_json.get('promoDescription'):
        item['summary'] = entry_json['promoDescription']['plaintext']
    elif entry_json.get('socialDescription'):
        item['summary'] = entry_json['socialDescription']['plaintext']

    item['content_html'] = ''
    if entry_json.get('dek'):
        item['content_html'] += '<p><em>{}</em></p>'.format(entry_json['dek']['html'])

    if entry_json.get('leadComponent'):
        item['content_html'] += render_body_component(entry_json['leadComponent'])

    if entry_json['type'] == 'QUICK_POST':
        for component in entry_json['body']['quickPostComponents']:
            item['content_html'] += render_body_component(component)
        if entry_json.get('quickAttachment'):
            item['content_html'] += render_body_component(entry_json['quickAttachment'])
    else:
        for component in entry_json['body']['components']:
            item['content_html'] += render_body_component(component)

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><br/><\2', item['content_html'])
    return item

def get_content(url, args, save_debug):
    next_data = get_next_data(url)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')

    entry_json = next((it['data']['entity'] for it in next_data['props']['pageProps']['hydration']['responses'] if it['operationName'] == 'EntityLayoutQuery'), None)
    return get_item(entry_json, args, save_debug)


def get_feed(args, save_debug=False):
    #  https://www.theverge.com/rss/full.xml
    if '/rss/' in args['url']:
        return rss.get_feed(args, save_debug, get_content)

    next_json = get_next_data(args['url'])
    if save_debug:
        utils.write_file(next_json, './debug/feed.json')

    entries = next((it['data']['entity']['recentEntries']['results'] for it in next_json['pageProps']['hydration']['responses'] if it['operationName'] == 'EntityLayoutQuery'), None)
    if not entries:
        entries = next((it['data']['community']['frontPage']['placements'] for it in next_json['pageProps']['hydration']['responses'] if it['operationName'] == 'FrontPageLayoutQuery'), None)
        if not entries:
            return None

    n = 0
    feed_items = []
    for it in entries:
        if it.get('placeable'):
            entry = it['placeable']
        else:
            entry = it
        if not entry.get('url'):
            continue
        if save_debug:
            logger.debug('getting content for ' + entry['url'])
        if entry['type'] == 'QUICK_POST':
            item = get_item(entry, args, save_debug)
        else:
            item = get_content(entry['url'], args, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
