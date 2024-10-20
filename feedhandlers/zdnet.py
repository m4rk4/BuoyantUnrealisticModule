import base64, hashlib, hmac, json, re, tldextract
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, secret_key, width=1092):
    # search secretKey
    split_url = urlsplit(img_src)
    m = re.search(r'/\d{4}/\d\d/\d\d/.*', split_url.path)
    if not m:
        logger.warning('unhandled image source ' + img_src)
        return img_src
    if 'tvguide' in split_url.netloc:
        img_path = '/hub' + m.group(0) + '?auto=webp&width={}'.format(width)
    else:
        img_path = m.group(0) + '?auto=webp&width={}'.format(width)
    img_path = re.sub(r'/watermark/[a-f0-9]+', '', img_path, flags=re.I)
    digest = hmac.new(bytes(secret_key, 'UTF-8'), bytes(img_path, 'UTF-8'), hashlib.sha1)
    return 'https://{}/a/img/resize/{}{}'.format(split_url.netloc, digest.hexdigest(), img_path)


def get_article_soup(url):
    article_html = utils.get_url_html(url)
    if not article_html:
        return None
    soup = BeautifulSoup(article_html, 'html.parser')
    return soup.find('article')


def get_content(url, args, site_json, save_debug=False):
    url = re.sub(r'#ftag=\w+', '', url)
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    slug = paths[-1]
    tld = tldextract.extract(url)
    secret_key = site_json['secret_key']
    if '/pictures/' in split_url.path:
        api_url = '{}/composer/{}/pages/gallery/{}/web?contentOnly=true&apiKey={}'.format(site_json['api_path'], tld.domain, slug, site_json['api_key'])
    elif '/video/' in split_url.path or '/videos/' in split_url.path:
        api_url = '{}/composer/{}/pages/video/{}/web?contentOnly=true&apiKey={}'.format(site_json['api_path'], tld.domain, slug, site_json['api_key'])
    # elif tld.domain == 'cnet' and ('/reviews/' in url or re.search(r'-review/?$', split_url.path)):
    #     page_html = utils.get_url_html(url)
    #     if not page_html:
    #         return None
    #     soup = BeautifulSoup(page_html, 'lxml')
    #     el = soup.find('meta', attrs={"name": "postId"})
    #     if not el:
    #         logger.warning('unknown postId in ' + url)
    #         return None
    #     slug = el['content']
    #     el = soup.find('link', attrs={"rel": "canonical"})
    #     if el:
    #         url = el['href']
    #     api_url = '{}/reviews/{}/{}/web?contentOnly=true&apiKey={}'.format(site_json['api_path'], tld.domain, slug, site_json['api_key'])
    else:
        api_url = '{}/composer/{}/pages/article/{}/web?contentOnly=true&apiKey={}'.format(site_json['api_path'], tld.domain, slug, site_json['api_key'])
    # print(api_url)
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if api_json.get('errors'):
        logger.warning('error code {}: {}'.format(api_json['errors'][0]['code'], api_json['errors'][0]['message']))
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    article_json = None
    api_component = None
    if api_json.get('components'):
        for api_component in api_json['components']:
            if api_component.get('data') and api_component['data'].get('id') and api_component['data']['id'] == slug:
                article_json = api_component['data']['item']
                break
    else:
        api_component = api_json
        article_json = api_component['data']['item']
    if not article_json:
        logger.warning('article not found in ' + api_url)
        return None

    article_soup = None

    item = {}
    item['id'] = article_json['id']
    item['url'] = utils.clean_url(url)
    item['title'] = article_json['headline']

    dt = datetime.fromisoformat(article_json['datePublished']['date']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if article_json.get('dateUpdated'):
        dt = datetime.fromisoformat(article_json['dateUpdated']['date']).replace(tzinfo=timezone.utc)
        item['date_modified'] = dt.isoformat()

    authors = []
    if article_json.get('author') and article_json['author'].get('lastName'):
        if article_json['author'].get('firstName'):
            authors.append('{} {}'.format(article_json['author']['firstName'], article_json['author']['lastName']))
        else:
            authors.append(article_json['author']['lastName'])
    if article_json.get('moreAuthors'):
        more_authors = []
        if isinstance(article_json['moreAuthors'], dict):
            if article_json['moreAuthors'].get('data'):
                more_authors = article_json['moreAuthors']['data']
        else:
            more_authors = article_json['moreAuthors']
        for it in more_authors:
            if it.get('firstName'):
                authors.append('{} {}'.format(it['firstName'], it['lastName']))
            else:
                authors.append(it['lastName'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    else:
        item['author'] = {"name": tld.domain}

    item['tags'] = []
    for it in article_json['topics']:
        item['tags'].append(it['name'])

    if article_json.get('promoImage'):
        item['_image'] = article_json['promoImage']['path']

    item['content_html'] = ''
    if article_json.get('dek'):
        item['summary'] = article_json['dek']
        item['content_html'] += '<p><em>{}</em></p>'.format(article_json['dek'])
    elif article_json.get('description'):
        item['summary'] = article_json['description']

    if api_component['meta']['componentName'] == 'video':
        item['_image'] = resize_image(article_json['image']['path'], secret_key)
        if article_json.get('mp4Url'):
            item['_video'] = article_json['mp4Url']
        elif article_json.get('files'):
            videos = []
            for it in article_json['files']:
                if it.get('streamingUrl') and it['streamingUrl'].endswith('mp4'):
                    videos.append(it)
            it = utils.closest_dict(videos, 'height', 480)
            item['_video'] = it['streamingUrl']
        if 'embed' in args:
            caption = item['title']
        else:
            caption = ''
        item['content_html'] += utils.add_video(item['_video'], 'video/mp4', item['_image'], caption)
        if article_json.get('description') and 'embed' not in args:
            item['content_html'] += '<p>{}</p>'.format(re.sub(r'(https://\S+)', r'<a href="\1">\1</a>', article_json['description']))
        soup = None

    elif api_component['meta']['componentName'] == 'gallery':
        gallery_html = ''
        n = len(article_json['items'])
        for i, it in enumerate(article_json['items']):
            caption = '{} of {}: '.format(i + 1, n)
            if it.get('photoCredit'):
                caption += it['photoCredit']
            else:
                caption += 'Credit: ' + item['author']['name']
            gallery_html += utils.add_image(resize_image(it['image']['path'], secret_key), caption)
            if it.get('title'):
                gallery_html += '<h3>{}</h3>'.format(it['title'])
            if it.get('description'):
                gallery_html += it['description']
            if i < n - 1:
                gallery_html += '<hr />'
            soup = BeautifulSoup(gallery_html, 'html.parser')

    elif api_component['meta']['componentName'] == 'review':
        if article_json.get('videos'):
            video_url = '{}://{}/videos/{}'.format(split_url.scheme, split_url.netloc, article_json['videos'][0]['slug'])
            if save_debug:
                logger.debug('getting content from ' + video_url)
            video_item = get_content(video_url, {"embed": True}, site_json, False)
            if video_item:
                item['_image'] = video_item['_image']
                item['content_html'] += video_item['content_html']
        elif article_json.get('image'):
            captions = []
            if article_json['image'].get('caption'):
                m = re.search(r'^<p>(.*)</p>', article_json['caption'])
                if m and m.group(1):
                    captions.append(m.group(1))
                else:
                    captions.append(article_json['caption'])
            if article_json['image'].get('credit'):
                captions.append(article_json['image']['credit'])
            item['_image'] = resize_image(article_json['image']['path'], secret_key)
            item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))
        item['content_html'] += '<div style="text-align:center;"><h3>{}</h3>'.format(article_json['preferredProductName'])
        if article_json.get('rating'):
            item['content_html'] += '<span style="font-size:2em; font-weight:bold;">{}</span>/10'.format(article_json['rating'])
        if article_json.get('editorsChoice'):
            item['content_html'] += '<br/><span style="margin-top:4em; background-color:red; color:white;">Editors Choice</span>'
        item['content_html'] += '</div>'
        if article_json.get('bottomLine'):
            item['content_html'] += '<h4 style="padding:2px; margin-bottom:0;">Bottom line</h4><p style="margin-top:0;">{}</p>'.format(article_json['bottomLine'])
        if article_json.get('good'):
            item['content_html'] += '<h4 style="margin-bottom:0;">&#128077;&nbsp;Pros</h4><ul style="margin-top:0;">'
            for it in list(filter(None, article_json['good'].split('~'))):
                item['content_html'] += '<li>{}</li>'.format(it.strip())
            item['content_html'] += '</ul>'
        if article_json.get('good'):
            item['content_html'] += '<h4 style="margin-bottom:0;">&#128078;&nbsp;Cons</h4><ul style="margin-top:0;">'
            for it in list(filter(None, article_json['bad'].split('~'))):
                item['content_html'] += '<li>{}</li>'.format(it.strip())
            item['content_html'] += '</ul>'
        if article_json.get('subRatings'):
            item['content_html'] += '<h4 style="margin-bottom:0;">Score breakdown</h4><table>'
            for it in article_json['subRatings']:
                if it.get('rating'):
                    item['content_html'] += '<tr><td>{}</td><td>{}</td></tr>'.format(it['name'], it['rating'])
            item['content_html'] += '</table><br/>'
        item['content_html'] += '<hr/>'
        soup = BeautifulSoup(article_json['body'], 'html.parser')

    else:
        #if article_json.get('layoutName') and (article_json['layoutName'] == 'bighero' or article_json['layoutName'] == 'text-over-hero') and article_json.get('promoImage'):
        if not article_json['body'].startswith('<shortcode') and article_json.get('promoImage'):
            # Add the lede image
            img_src = resize_image(article_json['promoImage']['path'], secret_key)
            captions = []
            if article_json['promoImage'].get('caption'):
                m = re.search(r'^<p>(.*)</p>', article_json['promoImage']['caption'])
                if m:
                    if len(m.group(1)) > 0:
                        captions.append(m.group(1))
                else:
                    captions.append(article_json['promoImage']['caption'])
            if article_json['promoImage'].get('credits'):
                captions.append(article_json['promoImage']['credits'])
            item['content_html'] += utils.add_image(img_src, ' | '.join(captions))
        soup = BeautifulSoup(article_json['body'], 'html.parser')

    if soup:
        for el in soup.find_all('shortcode'):
            new_html = ''
            if el['shortcode'] == 'image':
                img_src = ''
                if re.search(r'\d{4}/\d{2}/\d{2}', el['image-date-created']):
                    img_src = 'https://{}/a/img/{}/{}/{}'.format(split_url.netloc, el['image-date-created'], el['uuid'], el['image-filename'])
                else:
                    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', el['image-date-created'])
                    if m:
                        img_src = 'https://{}/a/img/{}/{}/{}/{}/{}'.format(split_url.netloc, m.group(1), m.group(2), m.group(3), el['uuid'], el['image-filename'])
                    else:
                        logger.warning('unknown image src format in ' + item['url'])
                if img_src:
                    if el.get('image-do-not-resize') and el['image-do-not-resize'] != 'true':
                        img_src = resize_image(img_src, secret_key)
                    captions = []
                    if el.get('image-caption'):
                        m = re.search(r'^<p>(.*)</p>', el['image-caption'])
                        if m:
                            if len(m.group(1)) > 0:
                                captions.append(m.group(1))
                        else:
                            captions.append(el['image-caption'])
                    if el.get('image-credit'):
                        captions.append(el['image-credit'])
                    new_html = utils.add_image(img_src, ' | '.join(captions))

            elif el['shortcode'] == 'video':
                if el.get('api'):
                    shortcode_json = json.loads(el['api'].replace('&quot;', '"'))
                    #utils.write_file(shortcode_json, './debug/shortcode.json')
                    if shortcode_json.get('mp4Url'):
                        new_html += utils.add_video(shortcode_json['mp4Url'], 'video/mp4', resize_image(shortcode_json['image']['path'], secret_key), shortcode_json['headline'])
                    elif shortcode_json.get('files'):
                        it = utils.closest_dict(shortcode_json['files']['data'], 'height', 480)
                        new_html += utils.add_video(it['streamingUrl'], 'video/mp4', resize_image(shortcode_json['image']['path'], secret_key), shortcode_json['headline'])
                else:
                    logger.warning('unhandled shortcode video with no api in ' + item['url'])

            elif el['shortcode'] == 'twitter_tweet' or el['shortcode'] == 'youtube_video':
                new_html += utils.add_embed(el['url'])

            elif el['shortcode'] == 'link':
                if el.get('inner-text'):
                    new_html += '<a href="{}">{}</a>'.format(el['href'], el['inner-text'])
                elif el.get('link-text'):
                    new_html += '<a href="{}">{}</a>'.format(el['href'], el['link-text'])
                else:
                    logger.warning('unknown link text in ' + item['url'])

            elif el['shortcode'] == 'cmganchorsatellitelink':
                # Is there an api call to get the link?
                link = ''
                if not article_soup:
                    article_soup = get_article_soup(item['url'])
                if article_soup:
                    for it in article_soup.find_all('a', string=el['link-text']):
                        if it.get('data-link-tracker-options') and 'link_anchor' in it['data-link-tracker-options']:
                            link = it['href']
                            break
                if link:
                    new_html += '<a href="{}">{}</a>'.format(link, el['link-text'])
                else:
                    logger.debug('unable to determine link for cmganchorsatellitelink {} in {}'.format(el['id'], item['url']))
                    new_html += '<span>{}</span>'.format(el['link-text'])

            elif el['shortcode'] == 'annotation':
                # Is there an api call to get the link?
                link = ''
                if not article_soup:
                    article_soup = get_article_soup(item['url'])
                if article_soup:
                    it = article_soup.find('a', attrs={"data-link-tracker-options": re.compile(r'{}\|{}'.format(el['type'], el['score']))})
                    if it:
                        link = '{}://{}{}'.format(split_url.scheme, split_url.netloc, it['href'])
                if link:
                    new_html += '<a href="{}">{}</a>'.format(link, el['text'])
                else:
                    logger.debug('unable to determine link for annotation {} in {}'.format(el['id'], item['url']))
                    new_html += '<span>{}</span>'.format(el['text'])

            elif el['shortcode'] == 'pullquote':
                new_html += utils.add_pullquote(el['quote'])

            elif el['shortcode'] == 'commercelinkshortcode':
                new_html = '<a href="{}">{}</a>'.format(el['raw-url'], el['link-shortcode-text'])

            elif el['shortcode'] == 'chart':
                chart_json = json.loads(el['chart'].replace('&quot;', '"'))
                # utils.write_file(chart_json, './debug/chart.json')
                new_html = '<h2>{}</h2>'.format(chart_json['chartName'])
                if chart_json.get('chart'):
                    new_html += '<table style="width:100%; border-collapse:collapse;">'
                    for i, row in enumerate(chart_json['chart']):
                        if i % 2 == 0:
                            new_html += '<tr style="background-color:#aaa;">'
                        else:
                            new_html += '<tr>'
                        for it in row:
                            new_html += '<td style="padding:12px 8px; border:1px solid black;">{}</td>'.format(it)
                        new_html += '</tr>'
                    new_html += '</table>'
                elif chart_json.get('products'):
                    max_rating = 0
                    for row in chart_json['products']:
                        rating = row['ratings'][0]
                        if rating.endswith('%'):
                            rating = float(rating[:-1])
                        else:
                            rating = int(rating.replace(',', ''))
                        max_rating = max(max_rating, rating)
                    for row in chart_json['products']:
                        rating = row['ratings'][0]
                        if rating.endswith('%'):
                            rating = float(rating[:-1])
                        else:
                            rating = int(rating.replace(',', ''))
                        pct = int(100*rating/max_rating)
                        if pct >= 50:
                            new_html += '<div style="border:1px solid black; border-radius:10px; display:flex; justify-content:space-between; padding-left:8px; padding-right:8px; margin-bottom:8px; background:linear-gradient(to right, lightblue {}%, white {}%);"><p>{}</p><p>{}</p></div>'.format(pct, 100-pct, row['productName'], row['ratings'][0])
                        else:
                            new_html += '<div style="border:1px solid black; border-radius:10px; display:flex; justify-content:space-between; padding-left:8px; padding-right:8px; margin-bottom:8px; background:linear-gradient(to left, white {}%, lightblue {}%);"><p>{}</p><p>{}</p></div>'.format(100-pct, pct, row['productName'], row['ratings'][0])
                if chart_json.get('explanation'):
                    new_html += '<div><small><b>Note:</b> {}</small></div>'.format(chart_json['explanation'])

            elif el['shortcode'] == 'cnetlisticle' or el['shortcode'] == 'cross_content_listicle':
                if el.get('imagegroup'):
                    shortcode_json = json.loads(el['imagegroup'].replace('&quot;', '"'))
                    # utils.write_file(shortcode_json, './debug/shortcode.json')
                    if shortcode_json.get('imageData') and shortcode_json['imageData'].get('id'):
                        img_src = resize_image(shortcode_json['imageData']['path'], secret_key)
                        captions = []
                        if shortcode_json.get('imageCaption'):
                            m = re.search(r'^<p>(.+)</p>', shortcode_json['imageCaption'])
                            if m:
                                captions.append(m.group(1))
                        if shortcode_json.get('imageCredit'):
                            captions.append(shortcode_json['imageCredit'])
                        new_html += utils.add_image(img_src, ' | '.join(captions))
                if el.get('hed'):
                    new_html += '<h3 style="margin-bottom:0;">{}</h3>'.format(el['hed'])
                if el.get('superlative'):
                    new_html += '<h5 style="margin-top:0; margin-bottom:0;">{}</h5>'.format(el['superlative'])
                if el.get('description'):
                    new_html += el['description']
                if el.get('merchantoffers'):
                    shortcode_json = json.loads(el['merchantoffers'].replace('&quot;', '"'))
                    for it in shortcode_json:
                        if it.get('offerPrice'):
                            label = '${:.2f} at {}'.format(float(it['offerPrice']), it['offerMerchant'])
                            new_html += utils.add_button(it['rawUrl'], label)
                        else:
                            label = 'View at ' + it['offerMerchant']
                            new_html += utils.add_button(it['rawUrl'], label)
                new_html += '<hr/><div>&nbsp;</div>'

            elif el['shortcode'] == 'reviewcard':
                shortcode_json = json.loads(el['api'].replace('&quot;', '"'))
                #utils.write_file(shortcode_json, './debug/shortcode.json')
                new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em; width:90%; margin:auto; padding:8px; border:1px solid #444; border-radius:10px;">'

                img_src = resize_image(shortcode_json['imageGroup']['imageData']['path'], secret_key)
                captions = []
                if shortcode_json['imageGroup'].get('caption'):
                    m = re.search(r'^<p>(.*)</p>', shortcode_json['imageGroup']['caption'])
                    if m and m.group(1):
                        captions.append(m.group(1))
                    else:
                        captions.append(shortcode_json['imageGroup']['caption'])
                if shortcode_json['imageGroup'].get('credit'):
                    captions.append(shortcode_json['imageGroup']['credit'])
                new_html += '<div style="flex:1; min-width:256px;"><img src="{}" style="width:100%;">'.format(img_src)
                if captions:
                    new_html += '<div><small>{}</small></div>'.format(' | '.join(captions))

                new_html += '<div style="text-align:center; padding-top:8px; font-size:1.1em; font-weight:bold;">{}</div>'.format(shortcode_json['productName'])
                if shortcode_json.get('rating'):
                    new_html += '<div style="text-align:center; padding-top:8px; font-size:2em; font-weight:bold;">{}</div>'.format(shortcode_json['rating'])
                new_html += '</div>'

                new_html += '<div style="flex:1; min-width:256px;">'
                new_html += '<div style="font-weight:bold;">Like</div><ul style=\'list-style-type:"👍&nbsp;"\'>'
                for it in list(filter(None, shortcode_json['like'].split('~'))):
                    new_html += '<li>{}</li>'.format(it.strip())
                new_html += '</ul><div style="font-weight:bold;">Don\'t Like</div><ul style=\'list-style-type:"👎&nbsp;"\'>'
                for it in list(filter(None, shortcode_json['dislike'].split('~'))):
                    new_html += '<li>{}</li>'.format(it.strip())
                new_html += '</ul></div>'

                new_html += '<div style="flex:1; min-width:256px;">'
                if shortcode_json.get('techProd') and shortcode_json['techProd'].get('resellers'):
                    for it in shortcode_json['techProd']['resellers']:
                        offer_url = utils.get_redirect_url(it['url'])
                        label = '${:.2f} at {}'.format(int(it['price']) / 100, it['name'])
                        new_html += utils.add_button(offer_url, label)
                else:
                    for it in shortcode_json['merchantOffers']:
                        offer_url = it['rawUrl']
                        if it.get('offerPrice'):
                            label = '${:.2f} at {}'.format(float(it['offerPrice']), it['offerMerchant'])
                        else:
                            label = 'View at ' + it['offerMerchant']
                        new_html += utils.add_button(offer_url, label)
                new_html += '</div></div><div>&nbsp;</div>'

            elif el['shortcode'] == 'newscard':
                new_html += utils.add_blockquote('<h3 style="margin-bottom:0;">What\'s happening</h3><p>{}</p><h3 style="margin-bottom:0;">Why it matters</h3><p>{}</p>'.format(el['whathappening'], el['whymatters']))

            elif el['shortcode'] == 'buybutton':
                new_html += utils.add_button(el['button-url'], el['button-text'])

            elif el['shortcode'] == 'commercebutton':
                new_html += utils.add_button(el['raw-url'], el['button-text'])

            elif el['shortcode'] == 'commercepromo':
                shortcode_json = json.loads(el['api'].replace('&quot;', '"'))
                # utils.write_file(shortcode_json, './debug/shortcode.json')
                new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em; width:90%; margin:auto; padding:8px; border:1px solid #444; border-radius:10px;">'
                img_src = resize_image(shortcode_json['imageGroup']['imageData']['path'], secret_key, 360)
                new_html += '<div style="flex:1; min-width:160px;"><img src="{}" style="width:100%;"></div>'.format(img_src)
                new_html += '<div style="flex:2; min-width:256px;"><div style="font-size:1.05em; font-weight:bold;">{}</div>'.format(shortcode_json['hed'])
                if shortcode_json.get('offerPrice') and shortcode_json['offerPrice'] != 'undefined':
                    offer_url = shortcode_json['offerUrl']
                    label = '${:.2f} at {}'.format(float(shortcode_json['offerPrice']), shortcode_json['offerMerchant'])
                    new_html += utils.add_button(offer_url, label)
                elif shortcode_json.get('techProd') and shortcode_json['techProd'].get('resellers'):
                    for it in shortcode_json['techProd']['resellers']:
                        offer_url = utils.get_redirect_url(it['url'])
                        label = '${:.2f} at {}'.format(int(it['price']) / 100, it['name'])
                        new_html += utils.add_button(offer_url, label)
                else:
                    offer_url = shortcode_json['offerUrl']
                    label = 'View at ' + shortcode_json['offerMerchant']
                    new_html += utils.add_button(offer_url, label)
                new_html += '</div></div><div>&nbsp;</div>'

            elif el['shortcode'] == 'pinbox':
                shortcode_json = json.loads(el['api'].replace('&quot;', '"'))
                #utils.write_file(shortcode_json, './debug/shortcode.json')
                new_html = '<h3>{}</h3><ul>'.format(shortcode_json['title'])
                for it in shortcode_json['content']:
                    new_html += '<li><a href="https://{}/article/{}">{}</a></li>'.format(split_url.netloc, it['slug'], it['title'])
                new_html += '</ul>'

            elif el['shortcode'] == 'codesnippet':
                if el['encoding'] == 'base64':
                    code = base64.b64decode(el['code']).decode('utf-8')
                    if 'infogram-embed' in code:
                        m = re.search(r'data-id="([^"]+)"', code)
                        new_html = utils.add_embed('https://e.infogram.com/{}?src=embed'.format(m.group(1)))
                    elif re.search(r'https://joinsubtext\.com/|myFinance-widget', code):
                        el.decompose()
                        continue
                    elif re.search(r'^<(h\d|br)\b', code):
                        new_html += code
                    elif re.search(r'^<iframe', code):
                        m = re.search(r'src="([^"]+)"', code)
                        if m:
                            new_html += utils.add_embed(m.group(1))
                    if not new_html:
                        logger.warning('unhandled codesnippet {} in {}'.format(code, item['url']))
                        el.decompose()
                else:
                    logger.warning('unhandled codesnippet encoding {} in {}'.format(el['encoding'], item['url']))
                    el.decompose()

            elif el['shortcode'] == 'gallery':
                shortcode_json = json.loads(el['api'].replace('&quot;', '"'))
                #utils.write_file(shortcode_json, './debug/shortcode.json')
                gallery_url = '{}://{}/pictures/{}'.format(split_url.scheme, split_url.netloc, shortcode_json['slug'])
                link = '{}/content?read&url={}'.format(config.server, quote_plus(gallery_url))
                caption = 'Gallery: <a href="{}">{}</a>'.format(link, shortcode_json['headline'])
                new_html += utils.add_image(resize_image(shortcode_json['promoImage']['path'], secret_key), caption, link=link)

            elif el['shortcode'] == 'newsletter' or el['shortcode'] == 'relatedlinks':
                el.decompose()

            else:
                logger.warning('unhandled shortcode {} in {}'.format(el['shortcode'], item['url']))

            if new_html:
                el.insert_after(BeautifulSoup(new_html, 'html.parser'))
                el.decompose()


        for el in soup.find_all('table', attrs={"data-title": True}):
            el['style'] = 'width:100%; border-collapse:collapse;'
            for i, it in enumerate(el.find_all('tr')):
                if i % 2 == 0:
                    it['style'] = 'background-color:#aaa;'
                else:
                    it['style'] = ''
            for it in el.find_all(['td', 'th']):
                it['style'] = 'padding:12px 8px; border:1px solid black;'

        for el in soup.select('p > strong:-soup-contains("Also:")'):
            it = el.find_parent('p')
            if it:
                it.decompose()

        item['content_html'] += str(soup)
        if item['content_html'].endswith('<hr/>'):
            item['content_html'] = item['content_html'][:-5]
    return item


def get_feed(url, args, site_json, save_debug=False):
    # https://www.cnet.com/rss/
    if '/rss' in args['url'] or '/feed' in args['url']:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    # TODO: CNET tag feeds
    # TODO: CNET author feeds
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    slug = paths[-1]
    tld = tldextract.extract(url)

    feed = None
    feed_title = ''
    urls = []

    if False:
        page_html = utils.get_url_html(url)
        if not page_html:
            return None
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('meta', attrs={"name": "postId"})
        if not el:
            logger.warning('unknown postId in ' + url)
            return None
        api_url = '{}/authors/{}/{}/search/recent/web?componentType=ContentList&componentName=author-recent&componentDisplayName=Recent&limit=10&apiKey={}'.format(site_json['api_path'], tld.domain, el['content'], site_json['api_key'])
        api_json = utils.get_url_json(api_url)
        if not api_json:
            return None
        if save_debug:
            utils.write_file(api_json, './debug/feed.json')
        for it in api_json['data']['items']:
            urls.append('{}://{}/{}/{}'.format(split_url.scheme, split_url.netloc, it['metaData']['section'], it['slug']))
        feed_title = soup.title.get_text()

    if '/authors/' in url or '/profiles/' in url:
        api_url = '{}/composer/{}/pages/author/{}/web?componentType=ContentList&componentName=author-recent&componentDisplayName=Recent&limit=10&apiKey={}'.format(site_json['api_path'], tld.domain, paths[1], site_json['api_key'])
        api_json = utils.get_url_json(api_url)
        if not api_json:
            return None
        if save_debug:
            utils.write_file(api_json, './debug/feed.json')
        for component in api_json['components']:
            if component['meta']['componentType'] == 'Author':
                if component['data']['item'].get('byline'):
                    feed_title = component['data']['item']['byline'] + ' | ' + split_url.netloc
                elif component['data']['item'].get('profile') and component['data']['item']['profile'].get('byline'):
                    feed_title = component['data']['item']['profile']['byline'] + ' | ' + split_url.netloc
            elif component['meta']['componentType'] == 'ContentList' or component['meta']['componentType'] == 'AuthorList':
                for it in component['data']['items']:
                    it_url = '{}://{}'.format(split_url.scheme, split_url.netloc)
                    if it['type'] == 'content_article':
                        it_url += '/{}/'.format(site_json['article_path'])
                    elif it['type'] == 'content_video':
                        it_url += '/videos/'
                    elif it['type'] == 'content_gallery':
                        it_url += '/pictures/'
                    else:
                        logger.warning('unhandled content type {} for ' + it['slug'])
                        continue
                    it_url += it['slug']
                    if it_url not in urls:
                        urls.append(it_url)
    elif '/meet-the-team/' in url:
        api_url = utils.clean_url(url)
        if not api_url.endswith('/'):
            api_url += '/'
        api_url += 'xhr/?o=1&t=&topic=&d=&offset=0'
        api_json = utils.get_url_json(api_url)
        if not api_json:
            return None
        if save_debug:
            utils.write_file(api_json, './debug/feed.json')
        for it in api_json['loadMore']['articles']:
            urls.append('{}://{}/{}/{}'.format(split_url.scheme, split_url.netloc, it['typeLabel'], it['slug']))
            if not feed_title:
                feed_title = it['author']['username'] + ' | ' + split_url.netloc
    elif '/topic/' in url:
        page_html = utils.get_url_html(url)
        if not page_html:
            return None
        soup = BeautifulSoup(page_html, 'lxml')
        feed_title = soup.title.get_text()
        el = soup.find(attrs={"data-component": "loadMore"})
        if not el:
            logger.warning('unable to find loadMore in ' + url)
            return None
        data_load_more = json.loads(el['data-load-more-options'])
        api_url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, data_load_more['url'])
        api_url += '?endpoint=' + quote_plus(data_load_more['data']['endpoint'])
        for key, val in data_load_more['data']['params'].items():
            api_url += '&params%5B{}%5D='.format(key)
            if val:
                api_url += val
        api_url += '&view=river_alt&familyName=listing&typeName=dynamic_listing&offset=0&initialLimit=0&limit=15&lastAssetId=&disableOldContent=false'
        api_json = utils.get_url_json(api_url)
        if not api_json:
            return None
        if save_debug:
            utils.write_file(api_json, './debug/feed.json')
        soup = BeautifulSoup(api_json['loadMore']['html'], 'html.parser')
        for el in soup.select('article > div > a'):
            urls.append('{}://{}{}'.format(split_url.scheme, split_url.netloc, el['href']))
    else:
        page_html = utils.get_url_html(url)
        if not page_html:
            return None
        m = re.search(r'meta:\{componentName:"([^"]+)",componentDisplayName:"[^"]*Latest[^"]*",componentType:"ContentList"\}', page_html)
        if not m:
            logger.warning('unable to find componentName in ' + url)
            return None
        api_url = '{0}/components/{1}/listing/filtered_listing/{2}/web?searchBy=id&fields=id,title,promoTitle,typeName,author(id,username,firstName,lastName,socialProfileIds,image,email,middleName,authorBio,title,suppressProfile,typeName,byline),datePublished,description,promoDescription,metaData(canonicalUrl,promoHeadline,label,url,slideCount,duration,typeTitle,hubTopicPathString,preferredProductName,rating,linkUrl,origin,reviewType),image(id,filename,dateCreated,alt,credits,caption,path,typeName,width,height,bucketPath,bucketType),slug,topic,primaryTopic,secondaryTopics,wordCount,content,filters&page=1&componentType=ContentList&componentName={2}&apiKey={3}'.format(site_json['api_path'], tld.domain, m.group(1), site_json['api_key'])
        api_json = utils.get_url_json(api_url)
        if not api_json:
            return None
        for it in api_json['data']['items']:
            path = split_url.path
            if not path.endswith('/'):
                path += '/'
            urls.append('{}://{}{}{}'.format(split_url.scheme, split_url.netloc, path, it['slug']))

    if args['url'] == 'https://www.zdnet.com/pictures/':
        feed_title = 'ZDNet | Photo Galleries'
        page_html = utils.get_url_html(args['url'])
        if not page_html:
            return None
        soup = BeautifulSoup(page_html, 'html.parser')
        for el in soup.find_all('article'):
            it = el.find('h3')
            if it.a:
                urls.append('https://www.zdnet.com' + it.a['href'])

    elif args['url'] == 'https://www.tvguide.com/news/':
        feed_title = 'TV Guide | Latest News'
        api_url = 'https://cmg-prod.apigee.net/v1/xapi/composer/tvguide/pages/door/news-door-global/web?contentOnly=true&apiKey=MKjirHWTcEGBEOp2z7fNqTOe670TbHSz'
        api_json = utils.get_url_json(api_url)
        if not api_json:
            return None
        if save_debug:
            utils.write_file(api_json, './debug/feed.json')
        for it in api_json['components'][1]['data']['items']:
            urls.append(args['url'] + it['slug'])

    if urls:
        n = 0
        feed = utils.init_jsonfeed(args)
        if feed_title:
            feed['title'] = feed_title
        feed_items = []
        for url in urls:
            if save_debug:
                logger.debug('getting content for ' + url)
            item = get_content(url, args, site_json, save_debug)
            if item:
                if utils.filter_item(item, args) == True:
                    feed_items.append(item)
                    n += 1
                    if 'max' in args:
                        if n == int(args['max']):
                            break
        feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
