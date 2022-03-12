import json, re
from datetime import datetime, timezone
from urllib.parse import quote_plus

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    src = '{}?resize={}:*'.format(utils.clean_url(img_src), width)
    if 'localhost' in config.server:
        src = '{}/image?url={}'.format(config.server, quote_plus(src))
    return src


def get_content(url, args, save_debug=False):
    is_video = False
    m = re.search(r'/article/([^/]+)/', url)
    if m:
        gql_url = 'https://www.vice.com/api/v1/graphql?query=query%20articleNoBodyComponents(%24web_id%3A%20ID%2C%20%24page%3A%20Int%2C%20%24per_page%3A%20Int%2C%20%24locale%3A%20String%2C%20%24site%3A%20String)%20%7B%0A%20%20articles(%0A%20%20%20%20web_id%3A%20%24web_id%0A%20%20%20%20page%3A%20%24page%0A%20%20%20%20per_page%3A%20%24per_page%0A%20%20%20%20locale%3A%20%24locale%0A%20%20%20%20site%3A%20%24site%0A%20%20)%20%7B%0A%20%20%20%20id%0A%20%20%20%20body_components_json%0A%20%20%20%20suggested_tweet%0A%20%20%20%20dek%0A%20%20%20%20locale%0A%20%20%20%20content_policy_scoped_locales%20%7B%0A%20%20%20%20%20%20label%0A%20%20%20%20%20%20url_fragment%0A%20%20%20%20%20%20__typename%0A%20%20%20%20%7D%0A%20%20%20%20publish_date%0A%20%20%20%20updated_at%0A%20%20%20%20display_type%0A%20%20%20%20embed_code%0A%20%20%20%20embed_id%0A%20%20%20%20embed_autoplay%0A%20%20%20%20embed_data%0A%20%20%20%20full_page_iframe_url%0A%20%20%20%20vmp_id%0A%20%20%20%20word_count%0A%20%20%20%20autoplay%0A%20%20%20%20clickthrough_url%0A%20%20%20%20social_description%0A%20%20%20%20social_title%0A%20%20%20%20html_page_title%0A%20%20%20%20age_required%0A%20%20%20%20birthday_required%0A%20%20%20%20nsfb%0A%20%20%20%20nsfw%0A%20%20%20%20web_id%0A%20%20%20%20title%0A%20%20%20%20slug%0A%20%20%20%20summary%0A%20%20%20%20url%0A%20%20%20%20alt_text%0A%20%20%20%20caption%0A%20%20%20%20credit%0A%20%20%20%20thumbnail_url%0A%20%20%20%20thumbnail_url_1_1%0A%20%20%20%20thumbnail_url_10_4%0A%20%20%20%20thumbnail_url_16_9%0A%20%20%20%20social_lede%20%7B%0A%20%20%20%20%20%20alt_text%0A%20%20%20%20%20%20caption%0A%20%20%20%20%20%20credit%0A%20%20%20%20%20%20thumbnail_url_10_4%0A%20%20%20%20%20%20thumbnail_url_16_9%0A%20%20%20%20%20%20thumbnail_url_1_1%0A%20%20%20%20%20%20__typename%0A%20%20%20%20%7D%0A%20%20%20%20topic_callout%20%7B%0A%20%20%20%20%20%20is_callout%0A%20%20%20%20%20%20callout_logo%20%7B%0A%20%20%20%20%20%20%20%20alt_text%0A%20%20%20%20%20%20%20%20thumbnail_url%0A%20%20%20%20%20%20%20%20thumbnail_url_1_1%0A%20%20%20%20%20%20%20%20thumbnail_url_16_9%0A%20%20%20%20%20%20%20%20__typename%0A%20%20%20%20%20%20%7D%0A%20%20%20%20%20%20callout_dek%0A%20%20%20%20%20%20url%0A%20%20%20%20%20%20name%0A%20%20%20%20%20%20__typename%0A%20%20%20%20%7D%0A%20%20%20%20sponsor%20%7B%0A%20%20%20%20%20%20id%0A%20%20%20%20%20%20name%0A%20%20%20%20%20%20category%0A%20%20%20%20%20%20__typename%0A%20%20%20%20%7D%0A%20%20%20%20section%20%7B%0A%20%20%20%20%20%20id%0A%20%20%20%20%20%20brand_name%0A%20%20%20%20%20%20brand_description%0A%20%20%20%20%20%20brand_attribution_svg_url%0A%20%20%20%20%20%20slug%0A%20%20%20%20%20%20title%0A%20%20%20%20%20%20ad_targeting_id%0A%20%20%20%20%20%20__typename%0A%20%20%20%20%7D%0A%20%20%20%20primary_topic%20%7B%0A%20%20%20%20%20%20name%0A%20%20%20%20%20%20id%0A%20%20%20%20%20%20slug%0A%20%20%20%20%20%20__typename%0A%20%20%20%20%7D%0A%20%20%20%20original_channel%20%7B%0A%20%20%20%20%20%20id%0A%20%20%20%20%20%20slug%0A%20%20%20%20%20%20name%0A%20%20%20%20%20%20__typename%0A%20%20%20%20%7D%0A%20%20%20%20topics%20%7B%0A%20%20%20%20%20%20name%0A%20%20%20%20%20%20id%0A%20%20%20%20%20%20slug%0A%20%20%20%20%20%20__typename%0A%20%20%20%20%7D%0A%20%20%20%20grapeshot_classes%0A%20%20%20%20content_policies%20%7B%0A%20%20%20%20%20%20id%0A%20%20%20%20%20%20url%0A%20%20%20%20%20%20urls%0A%20%20%20%20%20%20url_fragment%0A%20%20%20%20%20%20geo_code%0A%20%20%20%20%20%20language%0A%20%20%20%20%20%20__typename%0A%20%20%20%20%7D%0A%20%20%20%20contributions%20%7B%0A%20%20%20%20%20%20role_id%0A%20%20%20%20%20%20role%0A%20%20%20%20%20%20contributor%20%7B%0A%20%20%20%20%20%20%20%20full_name%0A%20%20%20%20%20%20%20%20id%0A%20%20%20%20%20%20%20%20slug%0A%20%20%20%20%20%20%20%20thumbnail_url_1_1%0A%20%20%20%20%20%20%20%20credit%0A%20%20%20%20%20%20%20%20caption%0A%20%20%20%20%20%20%20%20bio%0A%20%20%20%20%20%20%20%20location%20%7B%0A%20%20%20%20%20%20%20%20%20%20data%20%7B%0A%20%20%20%20%20%20%20%20%20%20%20%20address_components%20%7B%0A%20%20%20%20%20%20%20%20%20%20%20%20%20%20long_name%0A%20%20%20%20%20%20%20%20%20%20%20%20%20%20short_name%0A%20%20%20%20%20%20%20%20%20%20%20%20%20%20types%0A%20%20%20%20%20%20%20%20%20%20%20%20%20%20__typename%0A%20%20%20%20%20%20%20%20%20%20%20%20%7D%0A%20%20%20%20%20%20%20%20%20%20%20%20__typename%0A%20%20%20%20%20%20%20%20%20%20%7D%0A%20%20%20%20%20%20%20%20%20%20__typename%0A%20%20%20%20%20%20%20%20%7D%0A%20%20%20%20%20%20%20%20__typename%0A%20%20%20%20%20%20%7D%0A%20%20%20%20%20%20__typename%0A%20%20%20%20%7D%0A%20%20%20%20__typename%0A%20%20%7D%0A%7D%0A&operationName=articleNoBodyComponents&variables=%7B%22web_id%22%3A%22{}%22%2C%22site%22%3A%22vice%22%2C%22locale%22%3A%22en_us%22%7D'.format(m.group(1))
        gql_json = utils.get_url_json(gql_url)
        if not gql_json:
            return None
        article_json = gql_json['data']['articles'][0]
    elif '/video/' in url or 'video.vice.com' in url:
        # Alternate method - doesn't seem to work if video is on vicetv.com
        #m = re.search(r'video/([^/]+)/([^/]+)', url)
        #slug = m.group(1)
        #video_id = m.group(2)
        #t = int(datetime.utcnow().timestamp()) + 1440
        #val = ':'.join([video_id, "GET", str(t)])
        #signature = hashlib.sha512(bytes(val, 'UTF-8')).hexdigest()
        #api_url = 'https://vms.vice.com/en_us/video/preplay/{}?skipadstitching=1&_ad_unit=&_aid={}&_debug=0&exp={}&fbprebidtoken=&platform=desktop&rn=37749&sign={}&tvetoken=&mvpd='.format(video_id, slug, t, signature)
        #api_json = utils.get_url_json(api_url)
        video_url = utils.get_redirect_url(url)
        api_json = utils.get_url_json(utils.clean_url(video_url) + '?json=true')
        if not api_json:
            return None
        if save_debug:
            utils.write_file(api_json, './debug/debug.json')
        article_json = api_json['data']['video']
        is_video = True

    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['id']
    item['url'] = article_json['url']
    item['title'] = article_json['title']

    dt = datetime.fromtimestamp(article_json['publish_date']/1000).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromtimestamp(article_json['updated_at']/1000).replace(tzinfo=timezone.utc)
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if is_video:
        item['author']['name'] = article_json['episode']['season']['show']['title']
    else:
        authors = []
        for author in article_json['contributions']:
            if author['role'] == 'Author':
                authors.append(author['contributor']['full_name'])
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    if article_json.get('primary_topic'):
        item['tags'].append(article_json['primary_topic']['name'].strip())
    if article_json.get('topics'):
        for tag in article_json['topics']:
            item['tags'].append(tag['name'].strip())
    if not item.get('tags'):
        del item['tags']

    item['content_html'] = ''

    if article_json.get('dek'):
        item['summary'] = article_json['dek']
        item['content_html'] += '<p>{}</p>'.format(article_json['dek'])

    if article_json.get('thumbnail_url'):
        item['_image'] = article_json['thumbnail_url']
        captions = []
        if article_json.get('caption'):
            captions.append(article_json['caption'].strip())
        if article_json.get('credit'):
            captions.append(article_json['credit'].strip())
        if not is_video:
            item['content_html'] += utils.add_image(resize_image(item['_image']), ' | '.join(captions))
    else:
        captions = []

    if is_video:
        item['_video'] = 'https://edge-api.vice.com/v1/transcoder/manifests/video/{}.m3u8'.format(article_json['id'])
        if article_json.get('locked'):
            captions.insert(0, '<b>This video is locked</b>')
        item['content_html'] += utils.add_video(item['_video'], 'application/x-mpegURL', resize_image(item['_image']), ' | '.join(captions))
        item['content_html'] += '<p>{}</p>'.format(article_json['body'])
        return item

    if article_json.get('body_components_json'):
        body_json = json.loads(article_json['body_components_json'])
        if save_debug:
            utils.write_file(body_json, './debug/body.json')
        for block in body_json:
            if block['role'] == 'body':
                if block.get('dropcap'):
                    item['content_html'] += '<p><span style="float:left; font-size:4em; line-height:0.8em;">{}</span>{}</p><div style="float:clear;"></div>'.format(block['html'][0], block['html'][1:])
                else:
                    item['content_html'] += '<p>{}</p>'.format(block['html'])
            elif block['role'] == 'image':
                item['content_html'] += utils.add_image(resize_image(block['URL']), block['caption'])
            elif block['role'] == 'oembed' or block['role'] == 'instagram' or block['role'] == 'tweet' or block['role'] == 'youtube':
                item['content_html'] += utils.add_embed(block['URL'])
            elif block['role'] == 'blockquote':
                item['content_html'] += utils.add_blockquote(block['html'])
            elif block['role'] == 'pullquote':
                item['content_html'] += utils.add_pullquote(block['html'])
            elif block['role'] == 'divider':
                item['content_html'] += '<hr style="width:80%;"/>'
            elif block['role'] == 'product':
                product = block['products'][0]
                poster = resize_image(product['images'][0]['thumbnail_url'], 128)
                desc = '<small>{}</small><h4 style="margin-top:0; margin-bottom:0;">{}</h4><ul style="margin-top:0.3em;">'.format(product['brand']['name'], product['name'])
                for offer in product['retailers']:
                    if product['currency']['code'] == 'USD':
                        currency = '$'
                    elif product['currency']['code'] == 'GBP':
                        currency = '£'
                    else:
                        currency = product['currency']['code']
                    desc += '<li><a href="{}">{}{} on {}</a></li>'.format(offer['product_url'], currency, offer['price'], offer['retailer']['name'])
                desc += '</ul>'
                item['content_html'] += '<div style="margin-bottom:1em;"><img style="float:left; margin-right:8px;" src="{}"/><div style="overflow:hidden;">{}</div><div style="clear:left;"></div></div>'.format(poster, desc)
            elif block['role'] == 'article':
                pass
            else:
                m = re.search(r'heading(\d)', block['role'])
                if m:
                    item['content_html'] += '<h{0}>{1}</h{0}>'.format(m.group(1), block['html'])
                else:
                    logger.warning('unhandled body block role {} in {}'.format(block['role'], url))

    return item


def get_feed(args, save_debug=False):
    # https://www.vice.com/en/rss
    # https://www.vice.com/en/rss/section/tech
    # https://www.vicetv.com/en_us/rss
    return rss.get_feed(args, save_debug, get_content)
