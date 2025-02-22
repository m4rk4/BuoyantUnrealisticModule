import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import jwplayer, rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1200):
    src = utils.clean_url(img_src).split(';')[0]
    return src + ';resize({},_).jpeg?auto=webp'.format(width)


def get_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')

    page_soup = BeautifulSoup(page_html, 'lxml')
    el = page_soup.find('script', string=re.compile(r'postSeed'))
    if not el:
        logger.warning('unable to find postSeed in ' + url)
        return None

    post_json = {}
    m = re.search(r'postSeed = (\{.*?\}),\n', el.string)
    post_json['post_seed'] = json.loads(m.group(1))
    m = re.search(r'photoGroups = (\[.*?\]),\n', el.string)
    post_json['photo_groups'] = json.loads(m.group(1))
    m = re.search(r'photos = (\{.*?\})\n', el.string)
    post_json['photos'] = json.loads(m.group(1))
    if save_debug:
        utils.write_file(post_json, './debug/debug.json')

    item = {}
    item['id'] = post_json['post_seed']['id']
    item['url'] = 'https://www.unseenhistories.com/' + post_json['post_seed']['slug']
    item['title'] = post_json['post_seed']['title']

    dt = datetime.fromtimestamp(post_json['post_seed']['published_at']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['authors'] = []
    for el in page_soup.select('div.author-meta > div.author-details > span.name > a'):
        item['authors'].append({"name": el.get_text().strip()})
    if len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }

    item['tags'] = []
    el = page_soup.find('script', string=re.compile(r'storyCategoriesSeed '))
    if el:
        m = re.search(r'member: (\[.*?\]),?\n', el.string)
        if m:
            for tag in json.loads(m.group(1)):
                item['tags'].append(tag[1])
        m = re.search(r'community: (\[.*?\]),?\n', el.string)
        if m:
            for tag in json.loads(m.group(1)):
                item['tags'].append(tag[1])

    # if post_json['post_seed'].get('categories'):
    #     for val in post_json['post_seed']['categories'].values():
    #         item['tags'].append(val['name'])

    if len(item['tags']) == 0:
        del item['tags']

    item['content_html'] = ''
    el = page_soup.find('h2', attrs={"data-field-name": "subtitle"})
    if el:
        item['summary'] = el.get_text()
        item['content_html'] += '<p><em>' + item['summary'] + '</em></p>'

    el = page_soup.find(id='cover-image-container')
    if el and el.img:
        item['image'] = resize_image(el.img['src'])
        item['content_html'] += utils.add_image(item['image'])

    def format_content(content, dropcap=False):
        if 'class=' in content:
            content = re.sub(r'<(\w+) class="ql-align-center">', r'<\1 style="text-align:center;">', content)
            content = re.sub(r'<(\w+) class="ql-size-large">', r'<\1 style="font-size:1.2em;">', content)
            content = re.sub(r'<(\w+) class="ql-size-huge">', r'<\1 style="font-size:1.5em;">', content)
        if dropcap:
            content = re.sub(r'^(<[^>]+>)(<[^>]+>)?(\W*\w)', r'\1\2<span style="float:left; font-size:4em; line-height:0.8em;">\3</span>', content, 1)
            content += '<span style="clear:left;"></span>'
        return content

    for block in post_json['photo_groups']:
        if block['group_type'] == 'text':
            # TODO: check block['dropcap_option']
            if block.get('published_content'):
                item['content_html'] += format_content(block['published_content'], block['dropcap_option'])
            elif block.get('title'):
                item['content_html'] += '<h2>' + block['title'] + '</h2>'
            else:
                logger.warning('unhandled text group {} in {}'.format(block['id'], item['url']))
        elif block['group_type'] == 'captioned-single' or block['group_type'] == 'single':
            if str(block['id']) in post_json['photos']:
                photo = post_json['photos'][str(block['id'])][0]
                if not re.search(r'UH_Monogram|UH_Supported_by', photo['file_name'], flags=re.I):
                    img_src = resize_image(photo['asset_url'])
                    caption = photo['caption'] if photo.get('caption') else ''
                    if block['caption_align'] == 'right':
                        # Use wrap-reverse so that content is first when wrapped
                        item['content_html'] += '<div style="display:flex; flex-wrap:wrap-reverse; gap:16px 8px;">'
                        item['content_html'] += '<div style="flex:1; min-width:360px;">' + utils.add_image(img_src, caption, link=photo.get('link_url')) + '</div>'
                        item['content_html'] += '<div style="flex:1; min-width:360px;">'
                        if block.get('title'):
                            item['content_html'] += '<h2>' + block['title'] + '</h2>'
                        if block.get('published_content'):
                            if block['align'] == 'center':
                                item['content_html'] += '<div style="text-align:center;">' + format_content(block['published_content'], block['dropcap_option']) + '</div>'
                            else:
                                item['content_html'] += format_content(block['published_content'], block['dropcap_option'])
                        item['content_html'] += '</div></div><div>&nbsp;</div>'
                    elif block['caption_align'] == 'left':
                        item['content_html'] += '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
                        item['content_html'] += '<div style="flex:1; min-width:360px;">'
                        if block.get('title'):
                            item['content_html'] += '<h2>' + block['title'] + '</h2>'
                        if block.get('published_content'):
                            if block['align'] == 'center':
                                item['content_html'] += '<div style="text-align:center;">' + format_content(block['published_content'], block['dropcap_option']) + '</div>'
                            else:
                                item['content_html'] += format_content(block['published_content'], block['dropcap_option'])
                        item['content_html'] += '</div>'
                        item['content_html'] += '<div style="flex:1; min-width:360px;">' + utils.add_image(img_src, caption, link=photo.get('link_url')) + '</div>'
                        item['content_html'] += '</div><div>&nbsp;</div>'
                    else:
                        if block.get('title'):
                            item['content_html'] += '<h2>' + block['title'] + '</h2>'
                        if block.get('published_content'):
                            if block['align'] == 'center':
                                item['content_html'] += '<div style="text-align:center;">' + format_content(block['published_content'], block['dropcap_option']) + '</div>'
                            else:
                                item['content_html'] += format_content(block['published_content'], block['dropcap_option'])
                        item['content_html'] += utils.add_image(img_src, caption, link=photo.get('link_url'))
            else:
                logger.warning('unhandled captioned-single group {} in {}'.format(block['id'], item['url']))
        elif block['group_type'] == 'set':
            if str(block['id']) in post_json['photos']:
                gallery_images = []
                item['content_html'] += '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
                for i, photo in enumerate(post_json['photos'][str(block['id'])]):
                    img_src = resize_image(photo['asset_url'], 1800)
                    thumb = resize_image(photo['asset_url'], 640)
                    caption = photo['caption'] if photo.get('caption') else ''
                    gallery_images.append({"src": img_src, "caption": caption, "thumb": thumb})
                    item['content_html'] += '<div style="flex:1; min-width:360px;">' + utils.add_image(img_src, caption) + '</div>'
                if i % 2 == 0:
                    item['content_html'] += '<div style="flex:1; min-width:360px;">&nbsp;</div>'
                gallery_url = '{}/gallery?images={}'.format(config.server, quote_plus(json.dumps(gallery_images)))
                item['content_html'] += '</div><div><small><a href="{}" target="_blank">View as slideshow</a>'.format(gallery_url)
                if block.get('caption'):
                    item['content_html'] += '. ' + block['caption']
                item['content_html'] += '</small></div><div>&nbsp;</div>'
            else:
                logger.warning('unhandled set group {} in {}'.format(block['id'], item['url']))
        elif block['group_type'] == 'video':
            if block['video_type'] == 'youtube':
                item['content_html'] += utils.add_embed(block['video_embed']['url'])
            elif block['video_type'] == 'ex.custom' and block['video_embed']['html'].startswith('<iframe'):
                el = BeautifulSoup(block['video_embed']['html'], 'html.parser')
                if el.iframe['src'] != 'https://unseenhistories.substack.com/embed':
                    item['content_html'] += utils.add_embed(el.iframe['src'])
            elif block['video_type'] == 'ex.custom' and re.search(r'<div class="[a-z]"><h7>', block['video_embed']['html']):
                el = BeautifulSoup(block['video_embed']['html'], 'html.parser')
                item['content_html'] += '<p style="text-align:center; font-weight:bold;">' + el.h7.decode_contents() + '</p>'
            elif block['video_type'] == 'ex.custom' and block['video_embed']['html'] == '<hr>':
                item['content_html'] += '<div>&nbsp;</div><hr><div>&nbsp;</div>'
            else:
                logger.warning('unhandled video group {} in {}'.format(block['id'], item['url']))
        elif block['group_type'] == 'super-quote':
            caption = block['caption'] if block.get('caption') and 'optional quote citation' not in block['caption'] else ''
            item['content_html'] += utils.add_pullquote(block['title'], caption)
        else:
            logger.warning('unhandled group_type {} in {}'.format(block['group_type'], item['url']))

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
