import json, re, tldextract
from bs4 import BeautifulSoup
from urllib.parse import quote, urlsplit

import utils
from feedhandlers import rss, wp, wp_posts

import logging

logger = logging.getLogger(__name__)


def format_content(soup, item, site_json):
    split_url = urlsplit(item['url'])
    base_url = '{}://{}'.format(split_url.scheme, split_url.netloc)

    for el in soup.find_all(class_='dtcc-deeplink'):
        new_html = ''
        if el.get('data-type'):
            if el['data-type'] == 'deeplink-button':
                new_html = '<div style="text-align:center; margin:1em;"><span style="padding:0.4em; font-weight:bold; background-color:#cc311e;"><a href="{}" style="color:white;">{} &#10138;</a></span></div>'.format(utils.get_redirect_url(el['data-url']), el['data-cta'])
            elif el['data-type'] == 'deeplink-textlink':
                new_html = '<a href="{}">{}</a>'.format(utils.get_redirect_url(el['data-url']), el['data-cta'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            if el.parent and el.parent == 'p':
                el.parent.insert_after(new_el)
                el.parent.decompose()
            else:
                el.insert_after(new_el)
                el.decompose()
        else:
            logger.warning('unhandled dtcc-deeplink in ' + item['url'])

    for el in soup.find_all(class_=re.compile(r'dtcc-affiliate')):
        new_html = ''
        offer_url = 'https://ccp.digitaltrends.com/go/ccp/products/{}/offers?publisher_id=dt&sites=dt&articles=3274775'.format(el['data-pid'], item['id'])
        offer_json = utils.get_url_json(offer_url)
        if offer_json:
            #utils.write_file(offer_json, './debug/offer.json')
            if el['data-type'] == 'textlink':
                offer_price = offer_json['data']['offers'][0]['price']
                offer_url = utils.get_redirect_url(offer_json['data']['offers'][0]['url'])
                new_html += '<a href="{}">${}</a>'.format(offer_url, offer_price)
            elif el['data-type'] == 'scorecard-shop' or el['data-type'] == 'button':
                if len(offer_json['data']['offers']) == 1:
                    offer_price = offer_json['data']['offers'][0]['price']
                    offer_url = utils.get_redirect_url(offer_json['data']['offers'][0]['url'])
                    tld = tldextract.extract(offer_url)
                    new_html += '<div style="text-align:center; margin:1em;"><span style="padding:0.4em; font-weight:bold; background-color:#cc311e;"><a href="{}" style="color:white;">${} AT {} &#10138;</a></span></div>'.format(offer_url, offer_price, tld.domain.upper())
                else:
                    new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                    for offer in offer_json['data']['offers']:
                        offer_price = offer['price']
                        offer_url = utils.get_redirect_url(offer['url'])
                        tld = tldextract.extract(offer_url)
                        new_html += '<div style="flex:1; min-width:256px; margin:1em; text-align:center;"><span style="padding:0.4em; font-weight:bold; background-color:#cc311e;"><a href="{}" style="color:white;">${} AT {} &#10138;</a></span></div>'.format(offer_url, offer_price, tld.domain.upper())
                    new_html += '</div>'
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            it = el.find_parent(class_='m-shop')
            if it:
                it.insert_after(new_el)
                it.decompose()
            else:
                el.insert_after(new_el)
                el.decompose()
        else:
            logger.warning('unhandled dtcc-affiliate in ' + item['url'])

    for el in soup.find_all(class_='dtvideos-container'):
        new_html = ''
        if el['data-provider'] == 'jwplayer':
            it = el.find('script')
            if it:
                m = re.search(r'window\.DTVideos\.create\((.*?)\)\n', it.string)
                if m:
                    video_json = json.loads(m.group(1))
                    new_html = utils.add_embed('https://cdn.jwplayer.com/players/' + video_json['videoIds'][0])
        elif el['data-provider'] == 'youtube':
            it = el.find(class_='h-embedded-video')
            if it:
                new_html = utils.add_embed(it['data-url'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled dtvideos-container in ' + item['url'])

    for el in soup.find_all(class_='b-media'):
        #utils.write_file(str(el), './debug/debug.html')
        new_html = ''
        it = el.find(class_='b-media__title')
        if it:
            new_html += '<h3>{}</h3>'.format(it.get_text().strip())
        new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
        it = el.find(class_='b-media__poster')
        if it:
            img = it.find('img')
            if img:
                if img['src'].startswith('data:'):
                    img_src = img['data-dt-lazy-src']
                else:
                    img_src = img['src']
                new_html += '<div style="flex:1; min-width:256px;"><img src="{}" style="width:100%"/></div>'.format(img_src)
        new_html += '<div style="flex:1; min-width:256px;">'
        for it in el.find_all(class_='b-media__rating-item'):
            new_html += '<div>'
            img = it.find('img')
            if img:
                if img['src'].startswith('data:'):
                    img_src = img['data-dt-lazy-src']
                else:
                    img_src = img['src']
                if img_src.endswith('icon-imdb.svg'):
                    new_html += '<b>IMDB rating:</b> '
                elif img_src.endswith('icon-metacritic.svg'):
                    new_html += '<b>Metacritic rating:</b> '
                else:
                    logger.warning('unknown b-media__rating-item source in ' + item['url'])
                    new_html += '<b>Unknown rating:</b> '
            new_html += '{}</div>'.format(it.find(class_='b-media__rating-score').get_text().strip())
        new_html += '<br/>'
        it = el.find(class_='b-media__tv-rating')
        if it:
            new_html += '<div><b>Rated:</b> {}</div>'.format(it.get_text().strip().upper())
            it.decompose()
        it = el.find(class_='b-media__duration')
        if it:
            new_html += '<div><b>Duration:</b> {}</div>'.format(it.get_text().strip())
        new_html += '<br/>'
        for it in el.find_all(class_='b-media__info-item'):
            it.attrs = {}
            s = it.find('strong')
            if s:
                s.attrs = {}
                s.string = s.string.strip() + ':'
            s = it.find(class_='dt-clamp')
            if s:
                s.attrs = {}
            new_html += str(it)
        new_html += '</div></div>'
        it = el.find(class_="b-media__text")
        if it:
            new_html += it.decode_contents()
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='b-review'):
        new_html = ''
        it = el.find(class_='b-review__image')
        if it:
            img = it.find('img')
            if img:
                if img['src'].startswith('data:'):
                    img_src = img['data-dt-lazy-src']
                else:
                    img_src = img['src']
                new_html += utils.add_image(img_src) + '<div>&nbsp;</div>'
        it = el.find(class_='b-review__title')
        if it:
            new_html += '<div style="font-size:1.2em; font-weight:bold; text-align:center;">{}</div>'.format(it.get_text().strip())
        it = el.find(class_='b-review__rating')
        if it:
            n = len(it.find_all(class_='b-stars__s--2')) + 0.5*len(it.find_all(class_='b-stars__s--1'))
            new_html += '<div style="text-align:center;"><span style="font-size:2em; font-weight:bold;">{}</span>&nbsp;/&nbsp;'.format(n)
            n = len(it.find_all(class_='b-stars__s'))
            new_html += '{}</div>'.format(n)
        it = el.find(class_='b-review__award')
        if it:
            if it.get_text().strip() == 'DT Editors\' Choice':
                new_html += '<div style="text-align:center"><img src="https://www.digitaltrends.com/wp-content/themes/dt-stardust/assets/images/svg/award-ec.svg" style="width:128px;"/></div>'
            elif it.get_text().strip() == 'DT Recommended Product':
                new_html += '<div style="text-align:center"><img src="https://www.digitaltrends.com/wp-content/themes/dt-stardust/assets/images/svg/award-rp.svg" style="width:128px;"/></div>'
            else:
                logger.warning('unknown b-review__award in ' + item['url'])
        it = el.find(class_='b-review__quote')
        if it:
            new_html += '<div style="text-align:center"><em>{}</em></div>'.format(it.get_text().strip())
        new_html += '<div>&nbsp;</div><div style="display:flex; flex-wrap:wrap; gap:1em;">'
        for it in el.find_all(class_='b-review__list'):
            new_html += '<div style="flex:1; min-width:256px;"><span style="font-size:1.2em; font-weight:bold;">{}</span>'.format(it.find(class_='b-review__label').get_text().strip())
            ul = it.find(class_='b-review__list-inner')
            ul.attrs = {}
            new_html += str(ul) + '</div>'
        new_html += '</div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='b-versus-index'):
        new_html = '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
        for elm in el.find_all(class_='b-versus-item'):
            new_html += '<div style="flex:1; min-width:256px; text-align:center;">'
            it = elm.find(class_='b-versus-item__img')
            img = it.find('img')
            if img:
                if img['src'].startswith('data:'):
                    img_src = img['data-dt-lazy-src']
                else:
                    img_src = img['src']
            new_html += '<img src="{}" style="width:100%;" />'.format(img_src)
            new_html += '<h3>{}</h3>'.format(elm.find(class_='b-versus-item__title').get_text().strip())
            if elm.find(class_='b-versus-item__review'):
                new_html += '<div>'
                if elm.find(class_='b-versus-item__stars'):
                    for it in elm.find_all(class_='b-stars__s--2'):
                        new_html += '&starf;'
                    if elm.find(class_='b-stars__s--1'):
                        new_html += '&half;'
                it = elm.find(class_='b-versus-item__link')
                if it:
                    new_html += '&nbsp;<a href="{}">{}</a>'.format(it['href'], it.get_text().strip())
                new_html += '</div>'
            new_html += '</div>'
        new_html += '</div><div>&nbsp;</div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='b-content__item-image'):
        wp_posts.add_image(el, el, base_url)

    for el in soup.find_all(class_='b-product-attributes'):
        new_html = ''
        it = el.find(class_='b-product-attributes__review')
        if it:
            if it.get_text().strip():
                link = it.find('a', class_='b-product-attributes__link')
                if link:
                    new_html += '<p><a href="{}">{}</a>: '.format(link['href'], link.get_text().strip())
                    if it.find(class_='b-product-attributes__stars'):
                        n = len(it.find_all(class_='b-stars__s--2')) + 0.5 * len(it.find_all(class_='b-stars__s--1'))
                        new_html += '<strong>{} / {}</strong>'.format(n, len(it.find_all(class_='b-stars__s')))
                    new_html += '</p>'
            it.decompose()
        new_html += '<div>&nbsp;</div><div style="display:flex; flex-wrap:wrap; gap:1em;">'
        it = el.find(class_='b-product-attributes__list')
        if it:
            for col in el.find_all(class_='b-product-attributes__list-column'):
                new_html += '<div style="flex:1; min-width:256px;"><span style="font-size:1.2em; font-weight:bold;">{}</span><ul>'.format(col.find(class_='b-product-attributes__list-label').get_text().strip())
                for li in col.find_all('li'):
                    new_html += '<li>{}</li>'.format(li.get_text().strip())
                new_html += '</ul></div>'
            it.decompose()
        new_html += '</div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_before(new_el)
        el.unwrap()

    for el in soup.find_all(class_='b-cc-compact'):
        new_html = '<div>&nbsp;</div><div style="display:flex; flex-wrap:wrap; gap:1em;">'
        new_html += '<div style="flex:2; min-width:256px;">'
        it = el.find(class_='b-cc-compact__image')
        if it:
            img = it.find('img')
            if img:
                if img['src'].startswith('data:'):
                    img_src = img['data-dt-lazy-src']
                else:
                    img_src = img['src']
                new_html += '<img src="{}" style="float:left; width:128px;" />'.format(img_src)
        new_html += '<div>'
        it = el.find(class_='b-cc-compact__title')
        if it:
            new_html += '<div style="font-size:1.1em; font-weight:bold;">{}</div>'.format(it.get_text().strip())
        it = el.find(class_='b-cc-compact__text')
        if it:
            new_html += '<div style="font-size:0.8em;">{}</div>'.format(it.get_text().strip())
        new_html += '</div></div>'
        it = el.find(attrs={"data-pid": True})
        if it:
            offer_url = 'https://ccp.digitaltrends.com/go/ccp/products/{}/offers?publisher_id=dt&sites=dt&articles={}'.format(it['data-pid'], item['id'])
            offer_json = utils.get_url_json(offer_url)
            if offer_json:
                offer_price = offer_json['data']['offers'][0]['price']
                offer_url = utils.get_redirect_url(offer_json['data']['offers'][0]['url'])
                tld = tldextract.extract(offer_url)
                new_html += '<div style="flex:1; min-width:256px; text-align:left; margin:1em;"><span style="padding:0.4em; font-weight:bold; background-color:#cc311e;"><a href="{}" style="color:white;">${} AT {} &#10138;</a></span></div>'.format(offer_url, offer_price, tld.domain.upper())
        new_html += '</div><div>&nbsp;</div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='b-content__item-heading'):
        el.attrs = {}

    for el in soup.find_all(class_='b-article-faq__item-question'):
        el.attrs = {}
        el.name = 'h3'


def get_content(url, args, site_json, save_debug=False):
    return wp.get_content(url, args, site_json, save_debug, format_content)


def get_feed(url, args, site_json, save_debug=False):
    # TODO: substack feed
    return rss.get_feed(url, args, site_json, save_debug, get_content)
