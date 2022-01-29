import math, re
from datetime import datetime

from feedhandlers import rss
import config, utils

import logging
logger = logging.getLogger(__name__)


def resize_image(image, width=1000, crop_square=False):
    if not image.get('crops'):
        return '{}/image?height=128&width=128'.format(config.server)

    crop = image['crops']['original']
    h = crop['height']
    w = crop['width']
    x = crop['x']
    y = crop['y']

    if image.get('public_id'):
        img_id = image['public_id']
    elif image.get('publicId'):
        img_id = image['publicId']
    else:
        logger.warning('unknown image id')
        return '{}/image?height=128&width=128'.format(config.server)

    if crop_square:
        if h < w:
            x = float(w - h) / 2.0
            w = h
        else:
            y = float(h - w) / 2.0
            h = w
    img_src = 'https://img.thedailybeast.com/image/upload/c_crop,d_placeholder_euli9k,h_{},w_{},x_{},y_{}/dpr_1.5/c_limit,w_{}/fl_lossy,q_auto'.format(
        math.ceil(h), math.ceil(w), math.ceil(x), math.ceil(y), math.ceil(width / 1.5))
    if image.get('version'):
        img_src += '/v' + image['version']
    img_src += '/' + img_id
    return img_src


def add_image(image):
    img_src = resize_image(image)
    caption = ''
    if image.get('mobiledoc_caption'):
        for section in image['mobiledoc_caption']['sections']:
            caption = render_markup_section(section, image['mobiledoc_caption']['markups'])
    if caption.startswith('<p>'):
        caption = re.sub(r'^<[^>]+>|<\/[^>]+>$', '', caption)
    if image.get('credit'):
        if caption:
            caption += ' | '
        caption += image['credit']

    return utils.add_image(img_src, caption)


def render_markers(markers, markups):
    render_html = ''
    for marker in markers:
        if marker[0] == 0:
            # MARKUP_MARKER_TYPE
            start_tag = ''
            end_tag = ''
            if len(marker[1]) != 0:
                for i in marker[1]:
                    markup = markups[i]
                    start_tag += '<' + markup[0]
                    if len(markup) > 1:
                        for j in range(0, len(markup[1]), 2):
                            start_tag += ' {}="{}"'.format(markup[1][j], markup[1][j + 1])
                    start_tag += '>'
                    end_tag = '</{}>'.format(markup[0]) + end_tag
            render_html += start_tag + marker[3] + end_tag

        elif marker[0] == 1:
            # ATOM_MARKER_TYPE
            logger.warning('unhandled ATOM_MARKER_TYPE')
    return render_html


def render_markup_section(section, markups):
    return '<{0}>{1}</{0}>'.format(section[1], render_markers(section[2], markups))


def render_card(card, conversion_cards):
    card_html = ''
    if card[0] == 'pt-image':
        card_html = add_image(card[1])

    elif card[0] == 'pt-video-card':
        if card[1]['class'] == 'youtube':
            card_html = utils.add_embed(card[1]['content'])
        elif card[1]['class'] == 'other':
            m = re.search(r'^<iframe.*src="([^"]+)"', card[1]['content'])
            if m:
                card_html = utils.add_embed(m.group(1))
            else:
                logger.warning('unhandled pt-video-card class ' + card[1]['class'])
        else:
            logger.warning('unhandled pt-video-card class ' + card[1]['class'])

    elif card[0] == 'pt-social-card':
        if card[1].get('url'):
            card_html = utils.add_embed(card[1]['url'])
        elif card[1].get('content'):
            card_html = utils.add_embed(card[1]['content'])
        else:
            logger.warning('unknown embed url in pt-social-card')

    elif card[0] == 'pt-block-quote-card':
        quote = ''
        for section in card[1]['content']['mobiledoc']['sections']:
            quote = render_markup_section(section, card[1]['content']['mobiledoc']['markups'])
        card_html = utils.add_blockquote(quote)

    elif card[0] == 'pt-pull-quote-card':
        card_html = utils.add_pullquote(card[1]['content']['quote'], card[1]['content']['credit'])

    elif card[0] == 'pt-conversion-card':
        if not conversion_cards:
            logger.warning('no conversion_cards provided')
        else:
            for conv_card in conversion_cards:
                if int(conv_card['id']) == int(card[1]['promoItemId']):
                    if conv_card['expanded']:
                        card_html = add_image(conv_card['image'])
                        card_html += '<h3>{}</h3>'.format(conv_card['promoItemName'])
                        markups = conv_card['mobiledocSummary']['markups']
                        for section in conv_card['mobiledocSummary']['sections']:
                            card_html += render_markup_section(section, markups)
                        card_html += '<ul>'
                        for offer in conv_card['partnerButtons']:
                            link = utils.get_redirect_url(offer['partnerUrl'])
                            card_html += '<li><a href="{}">Buy at {}</a>'.format(link, offer['partnerName'])
                            if offer.get('price'):
                                card_html += ': ${}'.format(offer['price'])
                            card_html += '</li>'
                        card_html += '</ul><hr/>'
                    else:
                        if conv_card.get('image'):
                            img_src = resize_image(conv_card['image'], width=128, crop_square=True)
                            offers = ''
                            for offer in conv_card['partnerButtons']:
                                if offers:
                                    offers += '<br/>'
                                offers += '&bull;&nbsp;<a href="{}">Buy at {}</a>'.format(
                                    utils.get_redirect_url(offer['partnerUrl']),
                                    offer['partnerName'])
                                if offer.get('price'):
                                    offers += ': ${}'.format(offer['price'])
                            card_html = '<div><img style="height:128px; float:left; margin-right:8px;" src="{}"/><div><h4 style="margin-top:0; margin-bottom:0.5em;">{}</h4>{}</div><div style="clear:left;"></div>'.format(
                                img_src, conv_card['promoItemName'], offers)
                        else:
                            card_html = '<h4>{}</h4><ul>'.format(conv_card['promoItemName'])
                            for offer in conv_card['partnerButtons']:
                                card_html += '<li><a href="{}">Buy at {}</a>'.format(
                                    utils.get_redirect_url(offer['partnerUrl']),
                                    offer['partnerName'])
                                if offer.get('price'):
                                    card_html += ': ${}'.format(offer['price'])
                                card_html += '</li>'
                            card_html += '</ul>'
                    break

    elif card[0] == 'pt-section-break-card':
        if card[1]['content'].get('text'):
            card_html = '<div style="display:flex; width:100%; height:20px; align-items:center;"><div style="flex-grow:2; height: 1px; background-color:#000; border:1px #000 solid;"></div><h2 style="flex-basis:auto; flex-grow:0; margin:0px 5px 0px 5px; text-align:center;">{}</h2><div style="flex-grow:2; height: 1px; background-color:#000; border:1px #000 solid;"></div></div></div>'.format(
                card[1]['content']['text'])
        else:
            card_html = '<hr/>'

    elif re.search('pt-fancy-links-card|pt-tracking-pixel', card[0]):
        pass

    else:
        logger.warning('unhandled card type ' + card[0])

    return card_html


def get_content(url, args, save_debug=False):
    clean_url = utils.clean_url(url)
    article_json = utils.get_url_json(clean_url, headers={"Accept": "application/json"})
    if not article_json:
        return None
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['id']
    item['url'] = clean_url
    if article_json.get('title'):
        item['title'] = article_json['title'].strip()
    elif article_json.get('longHeadline'):
        item['title'] = article_json['longHeadline'].strip()

    dt = datetime.fromisoformat(article_json['publicationDate'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
    if article_json.get('modifiedDate'):
        dt = datetime.fromisoformat(article_json['modifiedDate'].replace('Z', '+00:00'))
        item['date_modified'] = dt.isoformat()
    elif article_json.get('updated_at'):
        dt = datetime.fromisoformat(article_json['updated_at'].replace('Z', '+00:00'))
        item['date_modified'] = dt.isoformat()

    authors = []
    for author in article_json['authors']:
        authors.append(author['name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if article_json.get('tags'):
        item['tags'] = []
        for tag in article_json['tags']:
            item['tags'].append(tag['name'])
    elif article_json['metadata'].get('metaTags'):
        for tag in article_json['metadata']['metaTags']:
            if tag['name'] == 'cXenseParse:tde-keywords':
                item['tags'] = tag['content'].split(tag['extraAttributes']['data-separator'])
    elif article_json.get('autoKeywords'):
        item['tags'] = article_json['autoKeywords'].copy()

    if article_json.get('main_image'):
        item['_image'] = article_json['main_image']['url']
    elif article_json.get('hero') and article_json['hero'].get('image'):
        item['_image'] = article_json['hero']['image']['url']
    elif article_json.get('images'):
        item['_image'] = article_json['images'][0]['url']
    elif article_json['metadata'].get('ogImages'):
        item['_image'] = article_json['metadata']['ogImages'][0]['url']

    item['summary'] = article_json['description']

    hero = ''
    if article_json.get('hero'):
        if article_json['hero'].get('video'):
            if article_json['hero']['video']['type'] == 'jw':
                m = re.search(r'src="([^"]+)"', article_json['hero']['video']['mixedContent'])
                hero = utils.add_embed(m.group(1))
            else:
                logger.warning('unhandled hero video type {} in {}'.format(article_json['hero']['video']['type'], url))
        if not hero and article_json['hero'].get('image'):
            hero = add_image(article_json['hero']['image'])
    if not hero and article_json.get('main_image'):
        hero = add_image(article_json['main_image'])

    item['content_html'] = ''
    if hero:
        item['content_html'] = hero

    if article_json.get('body'):
        cards = article_json['body']['cards']
        markups = article_json['body']['markups']
        sections = article_json['body']['sections']
    elif article_json.get('mobiledoc'):
        cards = article_json['mobiledoc']['cards']
        markups = article_json['mobiledoc']['markups']
        sections = article_json['mobiledoc']['sections']

    if article_json.get('conversionCards'):
        conversion_cards = article_json['conversionCards']
    else:
        conversion_cards = None

    for section in sections:
        if section[0] == 1:
            # MARKUP_SECTION_TYPE
            item['content_html'] += render_markup_section(section, markups)

        elif section[0] == 2:
            # IMAGE_SECTION_TYPE
            logger.warning('unhandled IMAGE_SECTION_TYPE in ' + url)

        elif section[0] == 3:
            # LIST_SECTION_TYPE
            item['content_html'] += '<{}>'.format(section[1])
            for li in section[2]:
                item['content_html'] += '<li>' + render_markers(li, markups) + '</li>'
            item['content_html'] += '</{}>'.format(section[1])

        elif section[0] == 10:
            # CARD_SECTION_TYPE
            item['content_html'] += render_card(cards[section[1]], conversion_cards)

        else:
            logger.warning('unknown section type {} in {}'.format(section[0], url))

    if article_json.get('read_it_at') and article_json['read_it_at'].get('url'):
        item['content_html'] += '<p>Read it at <a href="{}">{}</a></p>'.format(article_json['read_it_at']['url'],
                                                                               article_json['read_it_at']['name'])

    return item


def get_feed(args, save_debug=False):
    return rss.get_feed(args, save_debug, get_content)
