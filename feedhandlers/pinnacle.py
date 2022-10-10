import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)

def get_image_src(image, width=1000):
    return 'https://assets3.thrillist.com/v1/image/{}/{}x0/scale;webp=auto;jpeg_quality=60;progressive.jpg'.format(image['image_id'], width)


def add_image(image, width=1000):
    img_src = get_image_src(image, width)
    captions = []
    if image.get('caption'):
        captions.append(image['caption'])
    if image.get('credit_title'):
        captions.append(image['credit_title'])
    return utils.add_image(img_src, ' | '.join(captions))


def get_next_data(url):
    page_html = utils.get_url_html(url)
    soup = BeautifulSoup(page_html, 'html.parser')
    el = soup.find('script', id='__NEXT_DATA__')
    if not el:
        return None
    return json.loads(el.string)

def format_block(block):
    #print(block['id'])
    block_html = ''
    if block.get('children') and block.get('layerName'):
        if block['layerName'] == 'Container' or block['layerName'] == 'Text HTML':
            for blk in block['children']:
                block_html += format_block(blk)

        elif block['layerName'] == 'Pull Quote':
            quote = ''
            for blk in block['children']:
                quote += format_block(blk)
            quote = re.sub(r'^<p>(.*)</p>$', r'\1', quote)
            quote = re.sub(r'^<strong>(.*)</strong>$', r'\1', quote)
            block_html += utils.add_pullquote(quote)

        elif block['layerName'] == '1 Up Image':
            if not block['children'][0].get('layerName'):
                src = format_block(block['children'][0])
                if len(block['children']) > 1:
                    caption = format_block(block['children'][1])
                else:
                    caption = ''
                caption = re.sub(r'^<p>(.*)</p>$', r'\1', caption)
                if block['children'][0]['component']['name'] == 'Image':
                    block_html += utils.add_image(src, caption)
                elif block['children'][0]['component']['name'] == 'Video':
                    poster = '{}/image?url={}'.format(config.server, quote_plus(src))
                    block_html += utils.add_video(src, 'video/mp4', poster, caption)
                else:
                    logger.warning('1 Up Image block with unhandled component type {} {}'.format(block['children'][0]['component']['name'], block['id']))
                if len(block['children']) > 2:
                    logger.warning('1 Up Image block with more than 2 children in ' + block['id'])
            else:
                for blk in block['children']:
                    block_html += format_block(blk)

        elif block['layerName'] == 'Gallery Carousel':
            if block['children'][0]['layerName'] == 'Container':
                for slide in block['children'][0]['component']['options']['slides']:
                    src = format_block(slide['content'][0])
                    if len(slide['content']) > 1:
                        caption = format_block(slide['content'][1])
                    else:
                        caption = ''
                    caption = re.sub(r'^<p>(.*)</p>$', r'\1', caption)
                    block_html += utils.add_image(src, caption)
                    if len(slide['content']) > 2:
                        logger.warning('slide block with more than 2 components in ' + block['id'])

        elif re.search(r'^Image #\d+', block['layerName']):
            if block['children'][0]['component']['name'] == 'Image':
                block_html += format_block(block['children'][0])
            else:
                logger.warning('{} block with unhandled child component {} in {}'.format(block['layerName'], block['children'][0]['component']['name'], block['id']))
            if len(block['children']) > 1:
                logger.warning('{} block with more than 1 child in {}'.format(block['layerName'], block['id']))

        elif block['layerName'] == 'Tags' or block['layerName'] == 'Title' or block['layerName'] == 'Byline':
            pass

        else:
            logger.warning('unhandled block layerName {} {}'.format(block['layerName'], block['id']))

    elif block.get('component'):
        if block['component']['name'] == 'Text':
            block_html += block['component']['options']['text']

        elif block['component']['name'] == 'Image':
            block_html += block['component']['options']['image']

        elif block['component']['name'] == 'Video':
            block_html += block['component']['options']['video']

        else:
            logger.warning('unhandled block component name {} {}'.format(block['component']['name'], block['id']))

    else:
        logger.warning('unhandled block ' + block['id'])

    return block_html


def get_content(url, args, save_debug=False):
    print(url)
    split_url = urlsplit(url)
    api_url = 'https://{}/api/pages?pinn_url={}'.format(split_url.netloc, split_url.path[1:])
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if not api_json['page']:
        return None

    page_json = api_json['page']
    if save_debug:
        utils.write_file(page_json, './debug/debug.json')

    item = {}
    item['id'] = page_json['uuid']
    item['url'] = 'https://{}/{}'.format(split_url.netloc, page_json['canonical_url'])
    item['title'] = page_json['title']

    #dt = datetime.fromisoformat(page_json['processed_time'].replace('Z', '+00:00'))
    dt_loc = datetime.fromtimestamp(page_json['sort_time']['_seconds'])
    tz_loc = pytz.timezone('US/Eastern')
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    authors = []
    for it in page_json['author']:
        authors.append(it['display_name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    if page_json.get('tags'):
        item['tags'] += page_json['tags'].copy()
    if page_json.get('terms'):
        item['tags'] += page_json['terms'].copy()

    if page_json.get('main_image'):
        item['_image'] = get_image_src(page_json['main_image'])
    elif page_json.get('cover_images'):
        item['_image'] = get_image_src(page_json['cover_images']['default'])

    if page_json.get('teaser_text'):
        item['summary'] = page_json['teaser_text']

    item['content_html'] = ''
    if page_json.get('subheadline'):
        item['content_html'] += '<p><em>{}</em></p>'.format(page_json['subheadline'])

    if page_json['__typename'] == 'NodeArticle':
        if not re.search(r'Image|Video', page_json['elements'][0]['__typename']):
            if page_json.get('main_image'):
                item['content_html'] += add_image(page_json['main_image'])
            elif page_json.get('cover_images'):
                item['content_html'] += add_image(page_json['cover_images']['default'])

        for element in page_json['elements']:
            if element['__typename'] == 'ParagraphBodyText':
                item['content_html'] += element['text']

            elif element['__typename'] == 'ParagraphBodyWithDropcap':
                if element['text'].startswith('<p>'):
                    text = re.sub(element['dropcap']['text_to_replace'], '<span style="float:left; font-size:4em; line-height:0.8em;">{}</span>'.format(element['dropcap']['text_to_replace']), element['text'], 1)
                    text = re.sub('</p>', '</p><span style="clear:left;"></span>', text, 1)
                    item['content_html'] += text
                else:
                    item['content_html'] += element['text']

            elif element['__typename'] == 'ParagraphEditorsNote':
                item['content_html'] += '<p><small>{}</small></p>'.format(element['text'])

            elif element['__typename'] == 'ParagraphPullQuote':
                item['content_html'] += utils.add_pullquote(element['text'], element['attribution'])

            elif element['__typename'] == 'ParagraphContributor':
                img_src = '{}/image?url={}&width=80&height=80&mask=ellipse'.format(config.server, quote_plus(get_image_src(element, 80)))
                item['content_html'] += '<table style="width:100%;"><tr><td style="width:80px;"><img src="{}"/></td><td><strong>{}</strong><br/><small>{}</small></td></tr></table>'.format(img_src, element['name'], element['description'])

            elif element['__typename'] == 'ParagraphCtaButton':
                item['content_html'] += '<div style="display:inline; padding:10px; background-color:blue; border-radius:10px;"><a href="{}" style="text-decoration:none; color:white;">{}</a></div>'.format(element['url'], element['link_text'])

            elif element['__typename'] == 'ParagraphProduct':
                item['content_html'] += '<table><tr><td style="width:25%; vertical-align:top;"><img src="{}" style="width:100%;"/></td><td style="vertical-align:top;"><span style="font-size:1.1em; font-weight:bold;">{}</span><p><b>{}</b><br/>{}</p><span style="padding:10px; background-color:blue; border-radius:10px;"><a href="{}" style="text-decoration:none; color:white;">{}</a></span></td></tr></table>'.format(get_image_src({"image_id":element['image']}, 360), element['product_name'], element['subheadline'], element['text'], element['link'], element['cta_copy'])

            elif element['__typename'] == 'ParagraphShopProduct':
                item['content_html'] += add_image(element['image'])
                item['content_html'] += '<h3>{}</h3>'.format(element['text'])
                if element.get('sale_price'):
                    item['content_html'] += '${}&nbsp;<del>${}</del>{}<div style="display:inline; padding:10px; background-color:blue; border-radius:10px;"><a href="{}" style="text-decoration:none; color:white;">${} at {}</a></div><br/><br/>'.format(element['sale_price'], element['price'], element['description'], element['original_link'], element['sale_price'], element['retailer'])
                else:
                    item['content_html'] += '${}{}<div style="display:inline; padding:10px; background-color:blue; border-radius:10px;"><a href="{}" style="text-decoration:none; color:white;">${} at {}</a></div><br/><br/>'.format(element['price'], element['description'], element['original_link'], element['price'], element['retailer'])

            elif element['__typename'] == 'ParagraphMainImage' or element['__typename'] == 'ParagraphImage':
                item['content_html'] += add_image(element)

            elif element['__typename'] == 'ParagraphVideo':
                if element['source'] == 'youtube':
                    item['content_html'] += utils.add_embed('https://www.youtube.com/embed/{}'.format(element['video_id']))
                elif element['source'] == 'jwplayer':
                    if element.get('jwplayer_video_id'):
                        item['content_html'] += utils.add_embed('https://cdn.jwplayer.com/previews/{}'.format(element['jwplayer_video_id']))
                    elif element.get('video_id'):
                        item['content_html'] += utils.add_embed('https://cdn.jwplayer.com/previews/{}'.format(element['video_id']))
                    elif page_json['video'].get('playlist'):
                        item['content_html'] += utils.add_embed(page_json['video']['playlist'][0]['link'])
                else:
                    logger.warning('unhandled ParagraphVideo element source {} in {}'.format(element['source'], item['url']))

            elif element['__typename'] == 'ParagraphEmbedHtml':
                embed_html = ''
                soup = BeautifulSoup(element['html'], 'html.parser')
                if soup.iframe:
                    embed_html += utils.add_embed(soup.iframe['src'])
                elif element['type'] == 'twitter':
                    if element.get('embed_id'):
                        embed_html += utils.add_embed(utils.get_twitter_url(element['embed_id']))
                    else:
                        links = soup.find_all('a')
                        embed_html += utils.add_embed(links[-1]['href'])
                elif element['type'] == 'instagram':
                    if element.get('embed_id'):
                        embed_html += utils.add_embed('https://www.instagram.com/p/{}/'.format(element['embed_id']))
                    elif soup.blockquote:
                        embed_html += utils.add_embed(soup.blockquote['data-instgrm-permalink'])
                elif element['type'] == 'facebook':
                    embed_html += utils.add_embed(element['embed_id'])
                elif element['type'] == 'tiktok':
                    if soup.blockquote:
                        embed_html += utils.add_embed(soup.blockquote['cite'])
                if embed_html:
                    item['content_html'] += embed_html
                else:
                    logger.warning('unhandled ParagraphEmbedHtml element type {} in {}'.format(element['type'], item['url']))

            elif element['__typename'] == 'ParagraphRelatedPost' or element['__typename'] == 'ParagraphShopCarousel':
                pass

            else:
                logger.warning('unhandled content element {} in {}'.format(element['__typename'], item['url']))

    elif page_json['__typename'] == 'NodeSeries':
        ep = page_json['seasons'][-1]['episodes'][-1]
        ep_json = utils.get_url_json('https://{}/api/pages?pinn_uuid={}'.format(split_url.netloc, ep['uuid']))
        if save_debug:
            utils.write_file(ep_json, './debug/video.json')
        ep_item = get_content('https://{}/{}'.format(split_url.netloc, ep_json['page']['canonical_url']), args, save_debug)
        if ep_item:
            item['content_html'] += ep_item['content_html']
        item['content_html'] += '<p><a href="{}">Watch series</a></p>'.format(item['url'])

    elif page_json['__typename'] == 'NodeVideo':
        if page_json['video']['source'] == 'jwplayer':
            if page_json['video'].get('jwplayer_video_id'):
                item['content_html'] += utils.add_embed('https://cdn.jwplayer.com/previews/{}'.format(page_json['video']['jwplayer_video_id']))
            elif page_json['video'].get('playlist'):
                item['content_html'] += utils.add_embed(page_json['video']['playlist'][0]['link'])
        else:
            logger.warning('unknown NodeVideo video source {} in {}'.format(page_json['video']['source'], item['url']))
        if page_json.get('body_text'):
            item['content_html'] += page_json['body_text']['text']

    elif page_json['__typename'] == 'NodeBuilder':
        next_data = get_next_data(url)
        if save_debug:
            utils.write_file(next_data, './debug/next.json')
        for block in next_data['props']['pageProps']['content']['data']['blocks'][0]['children']:
            item['content_html'] += format_block(block)

    else:
        logger.warning('unknown page type {} in {}'.format(page_json['__typename'], item['url']))

    item['content_html'] = re.sub(r'<p><br></p>', '', item['content_html'])
    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><br/><\2', item['content_html'])
    return item


def get_feed(args, save_debug=False):
    split_url = urlsplit(args['url'])
    # https://feeds.groupninemedia.com/feeds/thrillist/discover-news
    if split_url.path.startswith('/feeds/'):
        return rss.get_feed(args, save_debug, get_content)
    next_data = get_next_data(args['url'])
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    article_urls = []
    if next_data['props']['pageProps']['initialState']['homepage'].get('contents'):
        for key, val in next_data['props']['pageProps']['initialState']['homepage']['contents'].items():
            for it in val:
                article_urls.append('https://{}/{}'.format(split_url.netloc, it['canonical_url']))

    if next_data['props']['pageProps']['initialState']['category'].get('contents'):
        for key, val in next_data['props']['pageProps']['initialState']['category']['contents'].items():
            for it in val:
                article_urls.append('https://{}/{}'.format(split_url.netloc, it['canonical_url']))

    if next_data['props']['pageProps']['initialState']['stack'].get('cards'):
        for it in next_data['props']['pageProps']['initialState']['stack']['cards']:
            article_urls.append('https://{}/{}'.format(split_url.netloc, it['canonical_url']))

    if next_data['props']['pageProps']['initialState']['series'].get('episodes'):
        for key, val in next_data['props']['pageProps']['initialState']['series']['episodes'].items():
            article_urls.append('https://{}/{}'.format(split_url.netloc, val['canonical_url']))

    feed_items = []
    for url in article_urls:
        if save_debug:
            logger.debug('getting content for ' + url)
        item = get_content(url, args, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)

    feed = utils.init_jsonfeed(args)
    feed['title'] = next_data['props']['pageProps']['initialState']['app']['config']['site_name']
    if next_data['props']['pageProps']['initialState']['page'].get('display_name'):
        feed['title'] += ' | ' + next_data['props']['pageProps']['initialState']['page']['display_name']
    feed_items = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    if 'max' in args:
        feed['items'] = feed_items[:int(args['max'])]
    else:
        feed['items'] = feed_items
    return feed
