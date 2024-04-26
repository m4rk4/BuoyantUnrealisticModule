import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit, quote_plus

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_article_by_slug(slug):
    api_url = 'https://api.semafor.com/content?query=*%5B%0A%20%20slug.current%20%3D%3D%20%22{}%22%0A%5D%20%7C%20order(updatedTimestamp%20desc)%7B%0A%20%20%22headline%22%3A%20headline.headline%2C%0A%20%20%22slug%22%3A%20slug.current%2C%0A%20%20description%2C%0A%20%20%22tragedy%22%3A%20(%22internal%3Atragedy%22%20in%20taglist.tags%5B%5D.value)%2C%0A%20%20%22seoDescription%22%3A%20seo.seoDescription%2C%0A%20%20%22intro%22%3A%20intro%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20body%5B%5D%7B%0A%20%20%20%20%20%20...%2C%0A%20%20%20%20%20%20%0A%20%20markDefs%5B%5D%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%0A%20%20_type%20%3D%3D%20%22internalLink%22%20%3D%3E%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%22slug%22%3A%20%40.internalLink-%3Eslug.current%0A%20%20%7D%0A%0A%20%20%7D%0A%2C%0A%20%20%20%20%20%20%0A%20%20_type%20%3D%3D%20%22imageEmbed%22%20%3D%3E%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%22imageEmbedExternalLink%22%3A%20imageEmbed.link.externalLink%2C%0A%20%20%20%20%22imageEmbedInternalLink%22%3A%20imageEmbed.link.internalLink-%3Eslug.current%2C%0A%20%20%7D%0A%0A%20%20%20%20%7D%0A%20%20%7D%2C%0A%20%20semaforms%5B%5D%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20_type%20%3D%3D%20%22scoop%22%20%3D%3E%20%7B%0A%20%20%20%20%20%20...%2C%0A%20%20%20%20%20%20scoop%5B%5D%20%7B%0A%20%20%20%20%20%20%20%20...%2C%0A%20%20%20%20%20%20%20%20%0A%20%20markDefs%5B%5D%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%0A%20%20_type%20%3D%3D%20%22internalLink%22%20%3D%3E%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%22slug%22%3A%20%40.internalLink-%3Eslug.current%0A%20%20%7D%0A%0A%20%20%7D%0A%2C%0A%20%20%20%20%20%20%20%20%0A%20%20_type%20%3D%3D%20%22imageEmbed%22%20%3D%3E%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%22imageEmbedExternalLink%22%3A%20imageEmbed.link.externalLink%2C%0A%20%20%20%20%22imageEmbedInternalLink%22%3A%20imageEmbed.link.internalLink-%3Eslug.current%2C%0A%20%20%7D%0A%0A%20%20%20%20%20%20%7D%0A%20%20%20%20%7D%2C%0A%20%20%7D%2C%0A%20%20%22location%22%3A%20geo.location%2C%0A%20%20%22ledePhoto%22%3A%20%7B%0A%20%20%20%20...ledePhoto.ledephoto.imageEmbed%2C%0A%20%20%20%20%22imageEmbedExternalLink%22%3A%20ledePhoto.ledephoto.imageEmbed.link.externalLink%2C%0A%20%20%20%20%22imageEmbedInternalLink%22%3A%20ledePhoto.ledephoto.imageEmbed.link.internalLink-%3Eslug.current%2C%0A%20%20%7D%2C%0A%20%20ledeVideo%2C%0A%20%20%22vertical%22%3A%20vertical.vertical%2C%0A%20%20%22verticalDisplay%22%3A%20verticalDisplay.verticalDisplay%2C%0A%20%20publishedTimestamp%2C%0A%20%20updatedTimestamp%2C%0A%20%20%22signal%22%3A%20signal%5B%5D%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20body%5B%5D%20%7B%0A%20%20%20%20%20%20...%2C%0A%20%20%20%20%20%20%0A%20%20markDefs%5B%5D%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%0A%20%20_type%20%3D%3D%20%22internalLink%22%20%3D%3E%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%22slug%22%3A%20%40.internalLink-%3Eslug.current%0A%20%20%7D%0A%0A%20%20%7D%0A%2C%0A%20%20%20%20%20%20children%5B%5D%20%7B%0A%20%20%20%20%20%20%20%20...%2C%0A%20%20%20%20%20%20%20%20content%5B%5D%20%7B%0A%20%20%20%20%20%20%20%20%20%20...%2C%0A%20%20%20%20%20%20%20%20%20%20%0A%20%20markDefs%5B%5D%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%0A%20%20_type%20%3D%3D%20%22internalLink%22%20%3D%3E%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%22slug%22%3A%20%40.internalLink-%3Eslug.current%0A%20%20%7D%0A%0A%20%20%7D%0A%2C%0A%20%20%20%20%20%20%20%20%7D%0A%20%20%20%20%20%20%7D%2C%0A%20%20%20%20%7D%0A%20%20%7D%2C%0A%20%20_id%2C%0A%20%20%22authors%22%3A%20author%5B%5D-%3E%20%7B%0A%20%20%22headshot%22%3A%20headshot.asset-%3Eurl%2C%0A%20%20name%2C%0A%20%20authorSlug%2C%0A%20%20_id%2C%0A%7D%2C%0A%20%20_createdAt%2C%0A%7D'.format(quote_plus(slug))
    api_json = utils.get_url_json(api_url)
    if api_json and api_json.get('result') and len(api_json['result']) > 0:
        return api_json['result'][0]
    return None


def get_article_by_id(id):
    api_url = 'https://api.semafor.com/content?query=*%5B%0A%20%20_id%20%3D%3D%20%22{}%22%0A%5D%20%7C%20order(updatedTimestamp%20desc)%7B%0A%20%20%22headline%22%3A%20headline.headline%2C%0A%20%20%22slug%22%3A%20slug.current%2C%0A%20%20description%2C%0A%20%20%22tragedy%22%3A%20(%22internal%3Atragedy%22%20in%20taglist.tags%5B%5D.value)%2C%0A%20%20%22seoDescription%22%3A%20seo.seoDescription%2C%0A%20%20%22intro%22%3A%20intro%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20body%5B%5D%7B%0A%20%20%20%20%20%20...%2C%0A%20%20%20%20%20%20%0A%20%20markDefs%5B%5D%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%0A%20%20_type%20%3D%3D%20%22internalLink%22%20%3D%3E%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%22slug%22%3A%20%40.internalLink-%3Eslug.current%0A%20%20%7D%0A%0A%20%20%7D%0A%2C%0A%20%20%20%20%20%20%0A%20%20_type%20%3D%3D%20%22imageEmbed%22%20%3D%3E%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%22imageEmbedExternalLink%22%3A%20imageEmbed.link.externalLink%2C%0A%20%20%20%20%22imageEmbedInternalLink%22%3A%20imageEmbed.link.internalLink-%3Eslug.current%2C%0A%20%20%7D%0A%0A%20%20%20%20%7D%0A%20%20%7D%2C%0A%20%20semaforms%5B%5D%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20_type%20%3D%3D%20%22scoop%22%20%3D%3E%20%7B%0A%20%20%20%20%20%20...%2C%0A%20%20%20%20%20%20scoop%5B%5D%20%7B%0A%20%20%20%20%20%20%20%20...%2C%0A%20%20%20%20%20%20%20%20%0A%20%20markDefs%5B%5D%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%0A%20%20_type%20%3D%3D%20%22internalLink%22%20%3D%3E%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%22slug%22%3A%20%40.internalLink-%3Eslug.current%0A%20%20%7D%0A%0A%20%20%7D%0A%2C%0A%20%20%20%20%20%20%20%20%0A%20%20_type%20%3D%3D%20%22imageEmbed%22%20%3D%3E%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%22imageEmbedExternalLink%22%3A%20imageEmbed.link.externalLink%2C%0A%20%20%20%20%22imageEmbedInternalLink%22%3A%20imageEmbed.link.internalLink-%3Eslug.current%2C%0A%20%20%7D%0A%0A%20%20%20%20%20%20%7D%0A%20%20%20%20%7D%2C%0A%20%20%7D%2C%0A%20%20%22location%22%3A%20geo.location%2C%0A%20%20%22ledePhoto%22%3A%20%7B%0A%20%20%20%20...ledePhoto.ledephoto.imageEmbed%2C%0A%20%20%20%20%22imageEmbedExternalLink%22%3A%20ledePhoto.ledephoto.imageEmbed.link.externalLink%2C%0A%20%20%20%20%22imageEmbedInternalLink%22%3A%20ledePhoto.ledephoto.imageEmbed.link.internalLink-%3Eslug.current%2C%0A%20%20%7D%2C%0A%20%20ledeVideo%2C%0A%20%20%22vertical%22%3A%20vertical.vertical%2C%0A%20%20%22verticalDisplay%22%3A%20verticalDisplay.verticalDisplay%2C%0A%20%20publishedTimestamp%2C%0A%20%20updatedTimestamp%2C%0A%20%20%22signal%22%3A%20signal%5B%5D%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20body%5B%5D%20%7B%0A%20%20%20%20%20%20...%2C%0A%20%20%20%20%20%20%0A%20%20markDefs%5B%5D%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%0A%20%20_type%20%3D%3D%20%22internalLink%22%20%3D%3E%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%22slug%22%3A%20%40.internalLink-%3Eslug.current%0A%20%20%7D%0A%0A%20%20%7D%0A%2C%0A%20%20%20%20%20%20children%5B%5D%20%7B%0A%20%20%20%20%20%20%20%20...%2C%0A%20%20%20%20%20%20%20%20content%5B%5D%20%7B%0A%20%20%20%20%20%20%20%20%20%20...%2C%0A%20%20%20%20%20%20%20%20%20%20%0A%20%20markDefs%5B%5D%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%0A%20%20_type%20%3D%3D%20%22internalLink%22%20%3D%3E%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%22slug%22%3A%20%40.internalLink-%3Eslug.current%0A%20%20%7D%0A%0A%20%20%7D%0A%2C%0A%20%20%20%20%20%20%20%20%7D%0A%20%20%20%20%20%20%7D%2C%0A%20%20%20%20%7D%0A%20%20%7D%2C%0A%20%20_id%2C%0A%20%20%22authors%22%3A%20author%5B%5D-%3E%20%7B%0A%20%20%22headshot%22%3A%20headshot.asset-%3Eurl%2C%0A%20%20name%2C%0A%20%20authorSlug%2C%0A%20%20_id%2C%0A%7D%2C%0A%20%20_createdAt%2C%0A%7D'.format(id)
    api_json = utils.get_url_json(api_url)
    if api_json and api_json.get('result') and len(api_json['result']) > 0:
        return api_json['result'][0]
    return None


def convert_unicode(matchobj):
    try:
        return matchobj.group(0).encode('latin1').decode('utf-8')
    except:
        return matchobj.group(0)


def resize_image(image, width=1200):
    img_src = re.sub('^image-', r'https://img.semafor.com/', image['asset']['_ref'])
    img_src = re.sub('-(\w+)$', r'.\1', img_src)
    return img_src + '?w={}&q=75&auto=format'.format(width)


def add_image(image):
    img_src = resize_image(image)
    captions = []
    if image.get('caption'):
        captions.append(image['caption'])
    if image.get('attribution'):
        captions.append(image['attribution'])
    elif image.get('credit'):
        captions.append(image['credit'])
    elif image.get('rteCredit'):
        credit = ''
        for blk in image['rteCredit']:
            credit += render_block(blk)
        captions.append(re.sub(r'^<p>(.*)</p>$', r'\1', credit, flags=re.S))
    return utils.add_image(img_src, ' | '.join(captions))


def render_block(block):
    content_html = ''
    footnotes = []
    if block['_type'] == 'block':
        if block.get('style'):
            if block['style'] == 'normal':
                if block.get('listItem'):
                    if block['listItem'] == 'bullet':
                        block_start_tag = '<ul><li>'
                        block_end_tag = '</li></ul>'
                    else:
                        block_start_tag = '<ol><li>'
                        block_end_tag = '</li></ol>'
                else:
                    block_start_tag = '<p>'
                    block_end_tag = '</p>'
            else:
                block_start_tag = '<{}>'.format(block['style'])
                block_end_tag = '</{}>'.format(block['style'])
        else:
            block_start_tag = '<p>'
            block_end_tag = '</p>'
        content_html += block_start_tag

        for child in block['children']:
            start_tag = ''
            end_tag = ''
            if child['_type'] == 'span':
                text = re.sub('[^\x00-\x7F]+', convert_unicode, child['text'])
            elif child['_type'] == 'footnote':
                start_tag = '<small><sup>'
                end_tag = '</sup></small>'
                text = child['number']
                footnotes.append(child.copy())
            elif child['_type'] == 'cta':
                start_tag = '<hr style="width:80%; margin:auto; border-top:1px dashed #ccc;"/>'
                text = ''
                for blk in child['content']:
                    text += render_block(blk)
                text = re.sub(r'</p>$', '&nbsp;&#10230;</p>', text)
            elif child['_type'] == 'oneClickSubscribe':
                text = '<a href="https://www.semafor.com/newsletters#{}">Sign up here</a>.'.format(child['audience'].lower())
            else:
                logger.warning('unhandled block child type ' + child['_type'])
            if child.get('marks'):
                for m in child['marks']:
                    #print(m)
                    mark = next((it for it in block['markDefs'] if it['_key'] == m), None)
                    if mark:
                        if mark['_type'] == 'link':
                            if mark.get('href'):
                                start_tag += '<a href="{}">'.format(mark['href'])
                            elif '@' in text:
                                start_tag += '<a href="mailto:{}">'.format(text)
                            else:
                                logger.warning('unhandled mark link')
                            end_tag = '</a>' + end_tag
                        elif mark['_type'] == 'internalLink':
                            article_json = get_article_by_id(mark['internalLink']['_ref'])
                            if article_json:
                                start_tag += '<a href="https://www.semafor.com{}">'.format(article_json['slug'])
                                end_tag = '</a>' + end_tag
                            else:
                                logger.warning('unable to get internalLink info')
                        else:
                            logger.warning('unhandled markDef type ' + mark['_type'])
                    else:
                        start_tag += '<{}>'.format(m)
                        end_tag = '</{}>'.format(m) + end_tag
            content_html += '{}{}{}'.format(start_tag, text, end_tag)

        content_html += block_end_tag

    elif block['_type'] == 'imageEmbed' or block['_type'] == 'insetImage':
        if block.get('image'):
            image = block['image']
        elif block.get('imageEmbed'):
            image = block['imageEmbed']
        else:
            image = None
            logger.warning('unhandled ' + block['_type'])
        if image:
            content_html += add_image(image)

    elif block['_type'] == 'imageContentsBlock':
        content_html += add_image(block['photo'])
        for child in block['contents']:
            content_html += render_block(child)

    elif block['_type'] == 'insetImageSlideshow':
        for image in block['slideshowImages']:
            content_html += add_image(image)

    elif block['_type'] == 'pullQuote':
        content_html += utils.add_pullquote(block['text'])

    elif block['_type'] == 'youtube' or block['_type'] == 'twitter':
        content_html += utils.add_embed(block['url'])

    elif block['_type'] == 'embedBlock':
        soup = BeautifulSoup(block['html'], 'html.parser')
        if soup.iframe:
            content_html += utils.add_embed(soup.iframe['src'])
        else:
            logger.warning('unhandled embedBlock content')

    elif block['_type'] == 'divider':
        if block.get('variant') and block['variant'] == 'dotted-rule':
            content_html += '<hr style="border-top:1px dashed black;" />'
        else:
            content_html += '<hr/>'

    elif block['_type'] == 'ad' or block['_type'] == 'relatedStories' or block['_type'] == 'donateButton':
        pass

    else:
        logger.warning('unhandled block type ' + block['_type'])

    if footnotes:
        content_html += '<table style="margin-left:1em; font-size:0.8em;">'
        for footnote in footnotes:
            footnote_html = ''
            for blk in footnote['content']:
                footnote_html += render_block(blk)
            content_html += '<tr><td style="vertical-align:top;">{}</td><td style="vertical-align:top;">{}</td></tr>'.format(footnote['number'], re.sub(r'^<p>(.*)</p>$', r'\1', footnote_html, flags=re.S))
        content_html += '</table><div>&nbsp;</div>'
    return content_html


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    article_json = get_article_by_slug(split_url.path)
    if not article_json:
        return None
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')
    return get_article(article_json, args, site_json, save_debug)


def get_article(article_json, args, site_json, save_debug):
    item = {}
    item['id'] = article_json['_id']
    item['url'] = 'https://www.semafor.com' + article_json['slug']
    item['title'] = re.sub('[^\x00-\x7F]+', convert_unicode, article_json['headline'])

    dt = datetime.fromisoformat(article_json['_createdAt'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if article_json.get('lastPublished'):
        dt = datetime.fromisoformat(article_json['lastPublished'].replace('Z', '+00:00'))
        item['date_modified'] = dt.isoformat()

    if article_json.get('author'):
        item['author'] = {"name": article_json['author']['name']}
    elif article_json.get('authors'):
        authors = []
        for it in article_json['authors']:
            authors.append(it['name'])
        if authors:
            item['author'] = {}
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    # TODO: tags
    item['tags'] = []
    if article_json.get('vertical'):
        item['tags'].append(article_json['vertical'])
    if article_json.get('location'):
        item['tags'].append(article_json['location'])
    if not item.get('tags'):
        del item['tags']

    item['content_html'] = ''
    if article_json.get('ledePhoto') and article_json['ledePhoto'].get('asset'):
        item['_image'] = resize_image(article_json['ledePhoto'])
        item['content_html'] += add_image(article_json['ledePhoto'])

    if article_json.get('seoDescription'):
        item['summary'] = article_json['seoDescription']

    if article_json.get('intro') and article_json['intro'].get('body'):
        for block in article_json['intro']['body']:
            item['content_html'] += render_block(block)

    if article_json.get('semaforms'):
        for i, semaform in enumerate(article_json['semaforms']):
            if i > 0:
                item['content_html'] += '<hr/>'
            if semaform.get('title'):
                item['content_html'] += '<h2>{}</h2>'.format(semaform['title'])
            if semaform['_type'] == 'scoop':
                for block in semaform['scoop']:
                    item['content_html'] += render_block(block)
            elif semaform['_type'] == 'generaform':
                for block in semaform['body']:
                    item['content_html'] += render_block(block)
            elif semaform['_type'] == 'reportersTake':
                if semaform['author'].get('shortName'):
                    item['content_html'] += '<h2>{}\'s View</h2>'.format(semaform['author']['shortName'])
                else:
                    # TODO: use api to query author by id
                    author = next((it for it in article_json['authors'] if it['_id'] == semaform['author']['_ref']), None)
                    if author:
                        item['content_html'] += '<h2>{}\'s View</h2>'.format(author['name'].split(' ')[0])
                    else:
                        item['content_html'] += '<h2>The Author\'s View</h2>'
                for block in semaform['thescoop']:
                    item['content_html'] += render_block(block)
            elif semaform['_type'] == 'knowMore':
                item['content_html'] += '<h2>Know More</h2>'
                for block in semaform['knowMore']:
                    item['content_html'] += render_block(block)
            elif semaform['_type'] == 'theViewFrom':
                item['content_html'] += '<h2>The View from {}</h2>'.format(semaform['where'])
                for block in semaform['theViewFrom']:
                    item['content_html'] += render_block(block)
            elif semaform['_type'] == 'roomForDisagreement':
                item['content_html'] += '<h2>Room For Disagreement</h2>'
                for block in semaform['roomForDisagreement']:
                    item['content_html'] += render_block(block)
            elif semaform['_type'] == 'furtherReading':
                item['content_html'] += '<h2>Notable</h2>'
                for block in semaform['furtherReading']:
                    item['content_html'] += render_block(block)
            elif semaform['_type'] == 'worldToday':
                item['content_html'] += '<h2>The World Today</h2>'
                for block in semaform['worldToday']:
                    item['content_html'] += render_block(block)
            elif semaform['_type'] == 'numbered':
                item['content_html'] += '<div style="font-size:1.5em; font-weight:bold">{}</div><h2>{}</h2>'.format(semaform['number'], semaform['headline'])
                for block in semaform['numbered']:
                    item['content_html'] += render_block(block)
            elif semaform['_type'] == 'topical':
                item['content_html'] += '<div style="font-size:1.5em; font-weight:bold">{}</div><h2>{}</h2>'.format(semaform['lable'], semaform['headline'])
                for block in semaform['topical']:
                    item['content_html'] += render_block(block)
            elif semaform['_type'] == 'story':
                story_json = get_article_by_id(semaform['internalShareUrl']['_ref'])
                if story_json:
                    item['content_html'] += '<h2><a href="https://www.semafor.com/{}">{}</a></h2>'.format(story_json['slug'], semaform['headline'])
                    if story_json.get('authors'):
                        authors = []
                        for it in story_json['authors']:
                            authors.append(it['name'])
                        if authors:
                            item['content_html'] += '<div>By ' + re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors)) + '</div>'
                else:
                    item['content_html'] += '<h2>{}</h2>'.format(semaform['headline'])
                for block in semaform['body']:
                    item['content_html'] += render_block(block)
            else:
                logger.warning('unhandled semaform type {} in {}'.format(semaform['_type'], item['url']))

    if article_json.get('signal'):
        item['content_html'] += '<hr/><h2>Signals</h2>'
        for signal in article_json['signal']:
            if signal.get('insightTitle'):
                item['content_html'] += '<div style="font-size:1.2em; font-weight:bold">{}</div>'.format(signal['insightTitle'])
            if signal.get('source'):
                if len(signal['source']) == 1:
                    item['content_html'] += '<div><small>Source: '
                else:
                    item['content_html'] += '<div><small>Sources: '
                item['content_html'] += ', '.join(signal['source']) + '</small></div>'
            for block in signal['body']:
                item['content_html'] += render_block(block)

    # Fix lists
    item['content_html'] = re.sub(r'</(ol|ul)><(ol|ul)>', '', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    feed_items = []
    feed_title = ''
    articles = []
    # Note: api only fetches articles in the last 60*60*24 seconds (1 day)
    if len(paths) == 0:
        api_url = 'https://api.semafor.com/content?query=*%5B%0A%20%20_type%20%3D%3D%20%22article%22%20%26%26%0A%20%20updatedTimestamp%20!%3D%20null%20%26%26%0A%20%20dateTime(updatedTimestamp)%20%3E%20dateTime(now())%20-%2060*60*24%20%26%26%0A%20%20!(_id%20in%20path(%27drafts.**%27))%0A%20%20%26%26%20(%20string%3A%3AstartsWith(documentVersion%2C%20%271.0.%27)%20)%0A%5D%20%7C%20order(updatedTimestamp%20desc)%7B%0A%20%20%22headline%22%3A%20headline.headline%2C%0A%20%20%22slug%22%3A%20slug.current%2C%0A%20%20description%2C%0A%20%20%22tragedy%22%3A%20(%22internal%3Atragedy%22%20in%20taglist.tags%5B%5D.value)%2C%0A%20%20%22seoDescription%22%3A%20seo.seoDescription%2C%0A%20%20%22intro%22%3A%20intro%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20body%5B%5D%7B%0A%20%20%20%20%20%20...%2C%0A%20%20%20%20%20%20%0A%20%20markDefs%5B%5D%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%0A%20%20_type%20%3D%3D%20%22internalLink%22%20%3D%3E%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%22slug%22%3A%20%40.internalLink-%3Eslug.current%0A%20%20%7D%0A%0A%20%20%7D%0A%2C%0A%20%20%20%20%20%20%0A%20%20_type%20%3D%3D%20%22imageEmbed%22%20%3D%3E%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%22imageEmbedExternalLink%22%3A%20imageEmbed.link.externalLink%2C%0A%20%20%20%20%22imageEmbedInternalLink%22%3A%20imageEmbed.link.internalLink-%3Eslug.current%2C%0A%20%20%7D%0A%0A%20%20%20%20%7D%0A%20%20%7D%2C%0A%20%20semaforms%5B%5D%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20_type%20%3D%3D%20%22scoop%22%20%3D%3E%20%7B%0A%20%20%20%20%20%20...%2C%0A%20%20%20%20%20%20scoop%5B%5D%20%7B%0A%20%20%20%20%20%20%20%20...%2C%0A%20%20%20%20%20%20%20%20%0A%20%20markDefs%5B%5D%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%0A%20%20_type%20%3D%3D%20%22internalLink%22%20%3D%3E%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%22slug%22%3A%20%40.internalLink-%3Eslug.current%0A%20%20%7D%0A%0A%20%20%7D%0A%2C%0A%20%20%20%20%20%20%20%20%0A%20%20_type%20%3D%3D%20%22imageEmbed%22%20%3D%3E%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%22imageEmbedExternalLink%22%3A%20imageEmbed.link.externalLink%2C%0A%20%20%20%20%22imageEmbedInternalLink%22%3A%20imageEmbed.link.internalLink-%3Eslug.current%2C%0A%20%20%7D%0A%0A%20%20%20%20%20%20%7D%0A%20%20%20%20%7D%2C%0A%20%20%7D%2C%0A%20%20%22location%22%3A%20geo.location%2C%0A%20%20%22ledePhoto%22%3A%20%7B%0A%20%20%20%20...ledePhoto.ledephoto.imageEmbed%2C%0A%20%20%20%20%22imageEmbedExternalLink%22%3A%20ledePhoto.ledephoto.imageEmbed.link.externalLink%2C%0A%20%20%20%20%22imageEmbedInternalLink%22%3A%20ledePhoto.ledephoto.imageEmbed.link.internalLink-%3Eslug.current%2C%0A%20%20%7D%2C%0A%20%20ledeVideo%2C%0A%20%20%22vertical%22%3A%20vertical.vertical%2C%0A%20%20%22verticalDisplay%22%3A%20verticalDisplay.verticalDisplay%2C%0A%20%20publishedTimestamp%2C%0A%20%20updatedTimestamp%2C%0A%20%20%22signal%22%3A%20signal%5B%5D%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20body%5B%5D%20%7B%0A%20%20%20%20%20%20...%2C%0A%20%20%20%20%20%20%0A%20%20markDefs%5B%5D%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%0A%20%20_type%20%3D%3D%20%22internalLink%22%20%3D%3E%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%22slug%22%3A%20%40.internalLink-%3Eslug.current%0A%20%20%7D%0A%0A%20%20%7D%0A%2C%0A%20%20%20%20%20%20children%5B%5D%20%7B%0A%20%20%20%20%20%20%20%20...%2C%0A%20%20%20%20%20%20%20%20content%5B%5D%20%7B%0A%20%20%20%20%20%20%20%20%20%20...%2C%0A%20%20%20%20%20%20%20%20%20%20%0A%20%20markDefs%5B%5D%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%0A%20%20_type%20%3D%3D%20%22internalLink%22%20%3D%3E%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%22slug%22%3A%20%40.internalLink-%3Eslug.current%0A%20%20%7D%0A%0A%20%20%7D%0A%2C%0A%20%20%20%20%20%20%20%20%7D%0A%20%20%20%20%20%20%7D%2C%0A%20%20%20%20%7D%0A%20%20%7D%2C%0A%20%20_id%2C%0A%20%20%22authors%22%3A%20author%5B%5D-%3E%20%7B%0A%20%20%22headshot%22%3A%20headshot.asset-%3Eurl%2C%0A%20%20name%2C%0A%20%20authorSlug%2C%0A%20%20_id%2C%0A%7D%2C%0A%20%20_createdAt%2C%0A%7D'
        api_json = utils.get_url_json(api_url)
        if api_json and api_json.get('result') and len(api_json['result']) > 0:
            articles = api_json['result']
            feed_title = 'Semafor'
    elif paths[0] == 'vertical':
        api_url = 'https://api.semafor.com/content?query=*%5B%0A%20%20_type%20%3D%3D%20%22article%22%20%26%26%0A%20%20vertical.vertical%20%3D%3D%20%22{}%22%20%26%26%0A%20%20updatedTimestamp%20!%3D%20null%20%26%26%0A%20%20dateTime(updatedTimestamp)%20%3E%20dateTime(now())%20-%2060*60*24%20%26%26%0A%20%20!(_id%20in%20path(%27drafts.**%27))%0A%20%20%26%26%20(%20string%3A%3AstartsWith(documentVersion%2C%20%271.0.%27)%20)%0A%5D%20%7C%20order(updatedTimestamp%20desc)%7B%0A%20%20%22headline%22%3A%20headline.headline%2C%0A%20%20%22slug%22%3A%20slug.current%2C%0A%20%20description%2C%0A%20%20%22tragedy%22%3A%20(%22internal%3Atragedy%22%20in%20taglist.tags%5B%5D.value)%2C%0A%20%20%22seoDescription%22%3A%20seo.seoDescription%2C%0A%20%20%22intro%22%3A%20intro%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20body%5B%5D%7B%0A%20%20%20%20%20%20...%2C%0A%20%20%20%20%20%20%0A%20%20markDefs%5B%5D%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%0A%20%20_type%20%3D%3D%20%22internalLink%22%20%3D%3E%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%22slug%22%3A%20%40.internalLink-%3Eslug.current%0A%20%20%7D%0A%0A%20%20%7D%0A%2C%0A%20%20%20%20%20%20%0A%20%20_type%20%3D%3D%20%22imageEmbed%22%20%3D%3E%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%22imageEmbedExternalLink%22%3A%20imageEmbed.link.externalLink%2C%0A%20%20%20%20%22imageEmbedInternalLink%22%3A%20imageEmbed.link.internalLink-%3Eslug.current%2C%0A%20%20%7D%0A%0A%20%20%20%20%7D%0A%20%20%7D%2C%0A%20%20semaforms%5B%5D%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20_type%20%3D%3D%20%22scoop%22%20%3D%3E%20%7B%0A%20%20%20%20%20%20...%2C%0A%20%20%20%20%20%20scoop%5B%5D%20%7B%0A%20%20%20%20%20%20%20%20...%2C%0A%20%20%20%20%20%20%20%20%0A%20%20markDefs%5B%5D%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%0A%20%20_type%20%3D%3D%20%22internalLink%22%20%3D%3E%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%22slug%22%3A%20%40.internalLink-%3Eslug.current%0A%20%20%7D%0A%0A%20%20%7D%0A%2C%0A%20%20%20%20%20%20%20%20%0A%20%20_type%20%3D%3D%20%22imageEmbed%22%20%3D%3E%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%22imageEmbedExternalLink%22%3A%20imageEmbed.link.externalLink%2C%0A%20%20%20%20%22imageEmbedInternalLink%22%3A%20imageEmbed.link.internalLink-%3Eslug.current%2C%0A%20%20%7D%0A%0A%20%20%20%20%20%20%7D%0A%20%20%20%20%7D%2C%0A%20%20%7D%2C%0A%20%20%22location%22%3A%20geo.location%2C%0A%20%20%22ledePhoto%22%3A%20%7B%0A%20%20%20%20...ledePhoto.ledephoto.imageEmbed%2C%0A%20%20%20%20%22imageEmbedExternalLink%22%3A%20ledePhoto.ledephoto.imageEmbed.link.externalLink%2C%0A%20%20%20%20%22imageEmbedInternalLink%22%3A%20ledePhoto.ledephoto.imageEmbed.link.internalLink-%3Eslug.current%2C%0A%20%20%7D%2C%0A%20%20ledeVideo%2C%0A%20%20%22vertical%22%3A%20vertical.vertical%2C%0A%20%20%22verticalDisplay%22%3A%20verticalDisplay.verticalDisplay%2C%0A%20%20publishedTimestamp%2C%0A%20%20updatedTimestamp%2C%0A%20%20%22signal%22%3A%20signal%5B%5D%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20body%5B%5D%20%7B%0A%20%20%20%20%20%20...%2C%0A%20%20%20%20%20%20%0A%20%20markDefs%5B%5D%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%0A%20%20_type%20%3D%3D%20%22internalLink%22%20%3D%3E%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%22slug%22%3A%20%40.internalLink-%3Eslug.current%0A%20%20%7D%0A%0A%20%20%7D%0A%2C%0A%20%20%20%20%20%20children%5B%5D%20%7B%0A%20%20%20%20%20%20%20%20...%2C%0A%20%20%20%20%20%20%20%20content%5B%5D%20%7B%0A%20%20%20%20%20%20%20%20%20%20...%2C%0A%20%20%20%20%20%20%20%20%20%20%0A%20%20markDefs%5B%5D%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%0A%20%20_type%20%3D%3D%20%22internalLink%22%20%3D%3E%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%22slug%22%3A%20%40.internalLink-%3Eslug.current%0A%20%20%7D%0A%0A%20%20%7D%0A%2C%0A%20%20%20%20%20%20%20%20%7D%0A%20%20%20%20%20%20%7D%2C%0A%20%20%20%20%7D%0A%20%20%7D%2C%0A%20%20_id%2C%0A%20%20%22authors%22%3A%20author%5B%5D-%3E%20%7B%0A%20%20%22headshot%22%3A%20headshot.asset-%3Eurl%2C%0A%20%20name%2C%0A%20%20authorSlug%2C%0A%20%20_id%2C%0A%7D%2C%0A%20%20_createdAt%2C%0A%7D'.format(paths[1])
        api_json = utils.get_url_json(api_url)
        if api_json and api_json.get('result') and len(api_json['result']) > 0:
            articles = api_json['result']
            feed_title = 'Semafor ' + paths[1].title()
    elif paths[0] == 'newsletters':
        if len(paths) == 1:
            page_html = utils.get_url_html(url)
            if page_html:
                args_copy = args.copy()
                soup = BeautifulSoup(page_html, 'lxml')
                for el in soup.find_all('a', class_=re.compile(r'styles_newsletterFrequencyLink__')):
                    # print(el['href'])
                    args_copy['url'] = 'https://www.semafor.com' + el['href'].replace('/latest', '')
                    nl_feed = get_feed(args_copy['url'], args_copy, site_json, save_debug)
                    if nl_feed and nl_feed.get('items'):
                        feed_items += nl_feed['items'].copy()
        else:
            api_url = 'https://api.semafor.com/content?query=*%5B%0A%20%20_type%20%3D%3D%20%22newsletter%22%20%26%26%0A%20%20vertical.vertical%20%3D%3D%20%22{}%22%20%26%26%0A%20%20updatedTimestamp%20!%3D%20null%20%26%26%0A%20%20dateTime(updatedTimestamp)%20%3E%20dateTime(now())%20-%2060*60*24%20%26%26%0A%20%20!(_id%20in%20path(%27drafts.**%27))%0A%20%20%26%26%20(%20string%3A%3AstartsWith(documentVersion%2C%20%271.0.%27)%20)%0A%5D%20%7C%20order(updatedTimestamp%20desc)%7B%0A%20%20%22headline%22%3A%20headline.headline%2C%0A%20%20%22slug%22%3A%20slug.current%2C%0A%20%20description%2C%0A%20%20%22tragedy%22%3A%20(%22internal%3Atragedy%22%20in%20taglist.tags%5B%5D.value)%2C%0A%20%20%22seoDescription%22%3A%20seo.seoDescription%2C%0A%20%20%22intro%22%3A%20intro%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20body%5B%5D%7B%0A%20%20%20%20%20%20...%2C%0A%20%20%20%20%20%20%0A%20%20markDefs%5B%5D%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%0A%20%20_type%20%3D%3D%20%22internalLink%22%20%3D%3E%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%22slug%22%3A%20%40.internalLink-%3Eslug.current%0A%20%20%7D%0A%0A%20%20%7D%0A%2C%0A%20%20%20%20%20%20%0A%20%20_type%20%3D%3D%20%22imageEmbed%22%20%3D%3E%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%22imageEmbedExternalLink%22%3A%20imageEmbed.link.externalLink%2C%0A%20%20%20%20%22imageEmbedInternalLink%22%3A%20imageEmbed.link.internalLink-%3Eslug.current%2C%0A%20%20%7D%0A%0A%20%20%20%20%7D%0A%20%20%7D%2C%0A%20%20semaforms%5B%5D%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20_type%20%3D%3D%20%22scoop%22%20%3D%3E%20%7B%0A%20%20%20%20%20%20...%2C%0A%20%20%20%20%20%20scoop%5B%5D%20%7B%0A%20%20%20%20%20%20%20%20...%2C%0A%20%20%20%20%20%20%20%20%0A%20%20markDefs%5B%5D%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%0A%20%20_type%20%3D%3D%20%22internalLink%22%20%3D%3E%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%22slug%22%3A%20%40.internalLink-%3Eslug.current%0A%20%20%7D%0A%0A%20%20%7D%0A%2C%0A%20%20%20%20%20%20%20%20%0A%20%20_type%20%3D%3D%20%22imageEmbed%22%20%3D%3E%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%22imageEmbedExternalLink%22%3A%20imageEmbed.link.externalLink%2C%0A%20%20%20%20%22imageEmbedInternalLink%22%3A%20imageEmbed.link.internalLink-%3Eslug.current%2C%0A%20%20%7D%0A%0A%20%20%20%20%20%20%7D%0A%20%20%20%20%7D%2C%0A%20%20%7D%2C%0A%20%20%22location%22%3A%20geo.location%2C%0A%20%20%22ledePhoto%22%3A%20%7B%0A%20%20%20%20...ledePhoto.ledephoto.imageEmbed%2C%0A%20%20%20%20%22imageEmbedExternalLink%22%3A%20ledePhoto.ledephoto.imageEmbed.link.externalLink%2C%0A%20%20%20%20%22imageEmbedInternalLink%22%3A%20ledePhoto.ledephoto.imageEmbed.link.internalLink-%3Eslug.current%2C%0A%20%20%7D%2C%0A%20%20ledeVideo%2C%0A%20%20%22vertical%22%3A%20vertical.vertical%2C%0A%20%20%22verticalDisplay%22%3A%20verticalDisplay.verticalDisplay%2C%0A%20%20publishedTimestamp%2C%0A%20%20updatedTimestamp%2C%0A%20%20%22signal%22%3A%20signal%5B%5D%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20body%5B%5D%20%7B%0A%20%20%20%20%20%20...%2C%0A%20%20%20%20%20%20%0A%20%20markDefs%5B%5D%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%0A%20%20_type%20%3D%3D%20%22internalLink%22%20%3D%3E%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%22slug%22%3A%20%40.internalLink-%3Eslug.current%0A%20%20%7D%0A%0A%20%20%7D%0A%2C%0A%20%20%20%20%20%20children%5B%5D%20%7B%0A%20%20%20%20%20%20%20%20...%2C%0A%20%20%20%20%20%20%20%20content%5B%5D%20%7B%0A%20%20%20%20%20%20%20%20%20%20...%2C%0A%20%20%20%20%20%20%20%20%20%20%0A%20%20markDefs%5B%5D%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%0A%20%20_type%20%3D%3D%20%22internalLink%22%20%3D%3E%20%7B%0A%20%20%20%20...%2C%0A%20%20%20%20%22slug%22%3A%20%40.internalLink-%3Eslug.current%0A%20%20%7D%0A%0A%20%20%7D%0A%2C%0A%20%20%20%20%20%20%20%20%7D%0A%20%20%20%20%20%20%7D%2C%0A%20%20%20%20%7D%0A%20%20%7D%2C%0A%20%20_id%2C%0A%20%20%22authors%22%3A%20author%5B%5D-%3E%20%7B%0A%20%20%22headshot%22%3A%20headshot.asset-%3Eurl%2C%0A%20%20name%2C%0A%20%20authorSlug%2C%0A%20%20_id%2C%0A%7D%2C%0A%20%20_createdAt%2C%0A%7D'.format(paths[1])
            api_json = utils.get_url_json(api_url)
            if api_json and api_json.get('result') and len(api_json['result']) > 0:
                articles = api_json['result']
                feed_title = 'Semafor ' + paths[1].title()
    elif paths[0] == 'author':
        # TODO: how to use api to query authorSlug
        page_html = utils.get_url_html(url)
        if page_html:
            soup = BeautifulSoup(page_html, 'lxml')
            for el in soup.find_all('script', string=re.compile(r'self\.__next_f\.push')):
                for m in re.findall(r'\\"slug\\":\\"([^"]+)\\"', el.string):
                    article = {"slug": m}
                    articles.append(article)

    if save_debug and articles:
        utils.write_file(articles, './debug/feed.json')

    n = 0
    # for article in next_data['props']['pageProps']['breakingNews'] + next_data['props']['pageProps']['featuredArticles']:
    for article in articles:
        article_url = 'https://www.semafor.com' + article['slug']
        if save_debug:
            logger.debug('getting content for ' + article_url)
        # item = get_content(url, args, site_json, save_debug)
        if article.get('_id'):
            item = get_article(article, args, site_json, save_debug)
        else:
            item = get_content(article_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    if feed_title:
        feed['title'] = feed_title
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed