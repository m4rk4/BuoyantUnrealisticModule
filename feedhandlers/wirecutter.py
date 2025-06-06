import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

import utils

import logging

logger = logging.getLogger(__name__)


def resize_image(src, width=1024):
    if not src.startswith('https'):
        if not src.startswith('wp-content'):
            img_src = 'https://cdn.thewirecutter.com/wp-content/media/' + src
        else:
            img_src = 'https://cdn.thewirecutter.com/' + src
    else:
        img_src = src
    #img_src = img_src.replace('wp-content/uploads', 'wp-content/media')
    split_url = urlsplit(img_src)
    return '{}://{}{}?auto=webp&width={}'.format(split_url.scheme, split_url.netloc, split_url.path, width)


def get_content(url, args, site_json, save_debug=False):
    article_html = utils.get_url_html(url)
    if not article_html:
        return None

    soup = BeautifulSoup(article_html, 'html.parser')
    next_data = soup.find('script', id='__NEXT_DATA__')
    if not next_data:
        return None

    next_json = json.loads(next_data.string)
    if save_debug:
        utils.write_file(next_json, './debug/debug.json')

    post_json = next_json['props']['pageProps']['post']

    item = {}
    item['id'] = post_json['guid']
    item['url'] = url
    if post_json.get('metaTitle'):
        item['title'] = post_json['metaTitle']
    else:
        item['title'] = post_json['title']

    dt = datetime.fromisoformat(post_json['modifiedDateISO']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

    authors = []
    for author in post_json['authors']:
        authors.append(author['displayName'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    tags = []
    if post_json.get('primaryTerms'):
        for tag in post_json['primaryTerms']:
            tags.append(tag)
    if post_json.get('auxiliaryTerms'):
        for tag in post_json['auxiliaryTerms']:
            tags.append(tag)
    if tags:
        item['tags'] = tags.copy()

    item['_image'] = resize_image(post_json['heroImage']['source'])
    item['summary'] = post_json['metaDescription']

    def format_section(section):
        end_tag = ''
        section_html = ''
        if section['type'] == 'tag':
            if re.search(r'^(b|i|em|h\d|li|ol|p|ul|span|strong|sub|sup|tbody|td|tr)$', section['name']):
                section_html += '<{}>'.format(section['name'])
                end_tag = '</{}>'.format(section['name'])

            elif section['name'] == 'a':
                href = section['attribs']['href']
                # if section['attribs'].get('class') and section['attribs']['class'] == 'product-link':
                #  href = utils.get_redirect_url(href)
                section_html += '<a href="{}">'.format(href)
                end_tag = '</a>'

            elif section['name'] == 'br':
                section_html += '<br/>'

            elif section['name'] == 'hr':
                section_html += '<hr/>'

            elif section['name'] == 'img':
                section_html += utils.add_image(resize_image(section['attribs']['src']))

            elif section['name'] == 'source':
                if section['attribs']['type'] == 'video/mp4':
                    if '.gif' in section['attribs']['src']:
                        m = re.search(r'^(.*\.gif)\?', section['attribs']['src'])
                        section_html += utils.add_image(m.group(1))
                    else:
                        section_html += utils.add_video(section['attribs']['src'], 'video/mp4')
                else:
                    logger.warning('unhandled source type {}'.format(section['attribs']['type']))

            elif section['name'] == 'iframe':
                section_html += utils.add_embed(section['attribs']['src'])

            elif section['name'] == 'figure':
                if not next((it for it in section['children'] if (it['type'] == 'tag' and it['name'] == 'iframe')), None):
                    logger.warning('unhandled figure section')

            elif section['name'] == 'table':
                section_html += '<table style="width:100%; border:1px solid black;">'
                end_tag = '</table><div>&nbsp;</div>'

            elif section['name'] == 'shortcode-callout':
                for callout in section['dbData']['callouts']:
                    link = ''
                    card_footer = ''
                    if callout.get('sources'):
                        for source in callout['sources']:
                            if source.get('rawUrl'):
                                if not link:
                                    link = source['rawUrl']
                                card_footer += utils.add_button(source['rawUrl'], source['price']['formatted'] + ' from ' + source['store'])
                    card_image = '<a href="{}" target="_blank"><div style="width:100%; height:100%; background:url(\'{}\'); background-position:center; background-size:cover; border-radius:10px 0 0 0;"></div></a>'.format(link, callout['images']['full'])
                    card_content = ''
                    if callout.get('ribbon'):
                        card_content += '<div style="color:red; font-weight:bold;">' + callout['ribbon'] + '</div>'
                    card_content += '<div style="font-size:1.05em; font-weight:bold; overflow:hidden; display:-webkit-box; -webkit-line-clamp:2; line-clamp:2; -webkit-box-orient:vertical;"><a href="{}">{}</a></div>'.format(link, callout['name'])
                    if callout.get('title'):
                        card_content += '<div style="margin-top:8px; overflow:hidden; display:-webkit-box; -webkit-line-clamp:2; line-clamp:2; -webkit-box-orient:vertical;">' + callout['title'] + '</div>'
                    if callout.get('description'):
                        card_content += '<div style="margin-top:8px; font-size:0.8em; overflow:hidden; display:-webkit-box; -webkit-line-clamp:2; line-clamp:2; -webkit-box-orient:vertical;">' + callout['description'] + '</div>'
                    section_html += utils.format_small_card(card_image, card_content, card_footer, content_style='padding:8px;', align_items='start') + '<div>&nbsp;</div>'

            elif section['name'] == 'shortcode-caption':
                img_link = ''
                img_src = ''
                video_src = ''
                video_type = ''
                captions = []
                for child in section['children']:
                    if child['type'] == 'tag' and child['name'] == 'img':
                        if not img_src:
                            if child.get('dbData') and child['dbData'].get('source'):
                                img_src = resize_image(child['dbData']['source'])
                            else:
                                img_src = resize_image(child['attribs']['src'])
                        else:
                            logger.warning('unhandled shortcode-caption with multiple images')
                    elif child['type'] == 'tag' and child['name'] == 'video':
                        source = next((it for it in child['children'] if (it['type'] == 'tag' and it['name'] == 'source')), None)
                        video_src = source['attribs']['src']
                        video_type = source['attribs']['type']
                        img_src = utils.clean_url(video_src)
                        if not img_src.endswith('.gif'):
                            img_src = ''
                    elif child['type'] == 'text':
                        if child['data'] != ' ':
                            captions.append(child['data'])
                    elif child['type'] == 'comment':
                        if child['data'] != ' ':
                            logger.warning('unhandled shortcode-caption comment ' + child['data'])
                    else:
                        logger.warning('unhandled shortcode-caption child type ' + child['type'])
                if section.get('dbData') and section['dbData'].get('credit'):
                    captions.append(section['dbData']['credit'])
                if img_src:
                    section_html += utils.add_image(img_src, ' | '.join(captions), link=img_link)
                elif video_src:
                    section_html += utils.add_video(video_src, video_type, '', ' | '.join(captions))

            elif section['name'] == 'shortcode-gallery':
                for image in section['dbData']:
                    captions = []
                    if image.get('excerpt'):
                        captions.append(image['excerpt'])
                    if image.get('credit'):
                        captions.append(image['credit'])
                    img_src = ''
                    if image.get('dbData'):
                        if image['dbData'].get('source'):
                            img_src = image['dbData']['source']
                        elif image['dbData'].get('full'):
                            img_src = image['dbData']['full']
                    if not img_src:
                        if image['imagePaths'].get('full'):
                            img_src = image['imagePaths']['full']
                        elif image['imagePaths'].get('file'):
                            img_src = image['imagePaths']['file']
                    if img_src:
                        section_html += utils.add_image(resize_image(img_src), ' | '.join(captions))
                    else:
                        logger.warning('unhandled shortcode-gallery image source')

            elif section['name'] == 'shortcode-pullquote':
                section_html += utils.open_pullquote()
                end_tag += utils.close_pullquote()

            elif section['name'] == 'div':
                if section.get('children'):
                    logger.warning('unhandled div section')

            elif section['name'] == 'adslot' or re.search(r'^(shortcode\-recirc|video)$', section['name']):
                # recirc is usually related articles
                pass

            else:
                logger.debug('unhandled tag {}' + section['name'])

        elif section['type'] == 'text':
            section_html += section['data']

        elif section['type'] == 'comment':
            if section['data'] != 'more':
                logger.warning('unhandled section type comment')

        else:
            logger.debug('unhandled section type {}'.format(section['type']))

        if section.get('children') and section['name'] != 'shortcode-caption':
            for child in section['children']:
                section_html += format_section(child)

        section_html += end_tag
        return section_html

    item['content_html'] = utils.add_image(resize_image(post_json['heroImage']['source']), post_json['heroImage']['caption'])

    if post_json.get('structuredLede'):
        for section in post_json['structuredLede']:
            item['content_html'] += format_section(section)
        item['content_html'] += '<hr/>'

    if post_json.get('structuredIntro'):
        for section in post_json['structuredIntro']:
            item['content_html'] += format_section(section)

    if post_json.get('structuredContent'):
        for section in post_json['structuredContent']:
            item['content_html'] += format_section(section)

    if post_json.get('chapters'):
        for chapter in post_json['chapters']:
            item['content_html'] += '<hr/><h3>{}</h3>'.format(chapter['title'])
            if chapter.get('body'):
                for section in chapter['body']:
                    item['content_html'] += format_section(section)
            if chapter.get('sources'):
                item['content_html'] += '<ol>'
                for section in chapter['sources']:
                    item['content_html'] += '<li><a href="{}">{}</a>, {}</li>'.format(section['url'], section['title'], section['publication'])
                item['content_html'] += '</ol>'

    if post_json.get('listSections'):
        for list in post_json['listSections']:
            if list.get('title'):
                item['content_html'] += '<h3><u>{}</u></h3>'.format(list['title'])
            for product_item in list['productItems']:
                if product_item.get('title'):
                    item['content_html'] += '<h3>{}</h3>'.format(product_item['title'])
                if product_item.get('body'):
                    body = json.loads(product_item['body'])
                    for section in body:
                        item['content_html'] += format_section(section)
                for product in product_item['products']:
                    item['content_html'] += '<div><img style="float:left; margin-right:8px; width:128px;" src="{}"/><div style="overflow:auto; display:block;"><b>{}</b><br/><a href="https://www.nytimes.com/wirecutter{}">{}</a><br/><small>&bull;&nbsp;<a href="{}">${:0.2f} at {}</a></small></div><div style="clear:left;"></div><br/>'.format(
                        product['relatedProductData']['productImageUrl'], product['relatedProductData']['productName'],
                        product['relatedPostLink'], product['title'],
                        product['relatedProductData']['sources'][0]['affiliateLink'],
                        int(product['relatedProductData']['sources'][0]['sourcePrice']) / 100,
                        product['relatedProductData']['sources'][0]['merchantName'])

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item
