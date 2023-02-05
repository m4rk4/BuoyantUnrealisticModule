import base64, hashlib, hmac, json, re, tldextract
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, secret_key, width=1092):
    split_url = urlsplit(img_src)
    m = re.search('/\d{4}/\d\d/\d\d/.*', split_url.path)
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
    sites_json = utils.read_json_file('./sites.json')
    api_key = sites_json[tld.domain]['apiKey']
    secret_key = sites_json[tld.domain]['secretKey']
    if '/pictures/' in split_url.path:
        api_url = 'https://cmg-prod.apigee.net/v1/xapi/galleries/{}/{}/web?apiKey={}&componentName=gallery&componentDisplayName=Gallery&componentType=Gallery'.format(tld.domain, slug, api_key)
    elif re.search(r'/videos?/', split_url.path):
        api_url = 'https://cmg-prod.apigee.net/v1/xapi/videos/{}/{}/web?apiKey={}&componentName=video&componentDisplayName=Video&componentType=Video'.format(tld.domain, slug, api_key)
    elif tld.domain == 'cnet' and re.search(r'-(preview|review)/?$', split_url.path):
        slug = re.sub(r'-(preview|review)/?$', '', slug)
        api_url = 'https://cmg-prod.apigee.net/v1/xapi/reviews/{}/{}/web?apiKey={}&componentName=review&componentDisplayName=Review&componentType=Review'.format(tld.domain, slug, api_key)
    else:
        api_url = 'https://cmg-prod.apigee.net/v1/xapi/articles/{}/{}/web?apiKey={}&componentName=article&componentDisplayName=Article&componentType=Article'.format(tld.domain, slug, api_key)
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    article_soup = None
    article_json = api_json['data']['item']
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

    if api_json['meta']['componentName'] == 'video':
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

    elif api_json['meta']['componentName'] == 'gallery':
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

    elif api_json['meta']['componentName'] == 'review':
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
                shortcode_json = json.loads(el['api'].replace('&quot;', '"'))
                #utils.write_file(shortcode_json, './debug/shortcode.json')
                if shortcode_json.get('mp4Url'):
                    new_html += utils.add_video(shortcode_json['mp4Url'], 'video/mp4', resize_image(shortcode_json['image']['path'], secret_key), shortcode_json['headline'])
                elif shortcode_json.get('files'):
                    it = utils.closest_dict(shortcode_json['files']['data'], 'height', 480)
                    new_html += utils.add_video(it['streamingUrl'], 'video/mp4', resize_image(shortcode_json['image']['path'], secret_key), shortcode_json['headline'])

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
                new_html = '<h2>{}</h2><table>'.format(chart_json['chartName'])
                for row in chart_json['chart']:
                    new_html += '<tr>'
                    for it in row:
                        new_html += '<td>{}</td>'.format(it)
                    new_html += '</tr>'
                new_html += '</table>'

            elif el['shortcode'] == 'cnetlisticle' or el['shortcode'] == 'cross_content_listicle':
                if el.get('imagegroup'):
                    shortcode_json = json.loads(el['imagegroup'].replace('&quot;', '"'))
                    #utils.write_file(shortcode_json, './debug/shortcode.json')
                    if shortcode_json.get('imageData'):
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
                            new_html += '<div style="width:250px; padding:10px; margin-bottom:1em; background-color:red; text-align:center;"><a href="{}" style="color:white;">${:.2f} at {}</a></div>'.format(it['rawUrl'], float(it['offerPrice']), it['offerMerchant'])
                        else:
                            new_html += '<div style="width:250px; padding:10px; margin-bottom:1em; background-color:red; text-align:center; color:white;"><a href="{}" style="color:white;"> View at {}</a></div>'.format(it['rawUrl'], it['offerMerchant'])
                new_html += '<hr/>'

            elif el['shortcode'] == 'reviewcard':
                shortcode_json = json.loads(el['api'].replace('&quot;', '"'))
                #utils.write_file(shortcode_json, './debug/shortcode.json')
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
                new_html = utils.add_image(img_src, ' | '.join(captions))
                new_html += '<div style="text-align:center;"><h3>{}</h3>'.format(shortcode_json['productName'])
                if shortcode_json.get('rating'):
                    new_html += '<span style="font-size:2em; font-weight:bold;">{}</span>/10'.format(shortcode_json['rating'])
                new_html += '</div>'
                new_html += '<h4 style="margin-bottom:0;">&#128077;&nbsp;Pros</h4><ul>'
                for it in list(filter(None, shortcode_json['like'].split('~'))):
                    new_html += '<li>{}</li>'.format(it.strip())
                new_html += '</ul><h4 style="margin-bottom:0;">&#128078;&nbsp;Cons</h4><ul>'
                for it in list(filter(None, shortcode_json['dislike'].split('~'))):
                    new_html += '<li>{}</li>'.format(it.strip())
                new_html += '</ul>'
                if shortcode_json.get('techProd') and shortcode_json['techProd'].get('resellers'):
                    for it in shortcode_json['techProd']['resellers']:
                        new_html += '<div style="width:250px; padding:10px; margin-bottom:1em; background-color:red; text-align:center;"><a href="{}" style="color:white;">${:.2f} at {}</a></div>'.format(utils.get_redirect_url(it['url']), int(it['price'])/100, it['name'])
                else:
                    for it in shortcode_json['merchantOffers']:
                        if it.get('offerPrice'):
                            new_html += '<div style="width:250px; padding:10px; margin-bottom:1em; background-color:red; text-align:center;"><a href="{}" style="color:white;">${:.2f} at {}</a></div>'.format(it['rawUrl'], float(it['offerPrice']), it['offerMerchant'])
                        else:
                            new_html += '<div style="width:250px; padding:10px; margin-bottom:1em; background-color:red; text-align:center; color:white;"><a href="{}" style="color:white;"> View at {}</a></div>'.format(it['rawUrl'], it['offerMerchant'])

            elif el['shortcode'] == 'newscard':
                new_html += utils.add_blockquote('<h3 style="margin-bottom:0;">What\'s happening</h3><p>{}</p><h3 style="margin-bottom:0;">Why it matters</h3><p>{}</p>'.format(el['whathappening'], el['whymatters']))

            elif el['shortcode'] == 'buybutton':
                new_html += '<div style="width:250px; padding:10px; margin-bottom:1em; background-color:red; text-align:center; color:white;"><a href="{}" style="color:white;">{}</a></div>'.format(el['button-url'], el['button-text'])

            elif el['shortcode'] == 'commercebutton':
                new_html += '<div style="width:250px; padding:10px; margin-bottom:1em; background-color:red; text-align:center; color:white;"><a href="{}" style="color:white;">{}</a></div>'.format(el['raw-url'], el['button-text'])

            elif el['shortcode'] == 'commercepromo':
                shortcode_json = json.loads(el['api'].replace('&quot;', '"'))
                #utils.write_file(shortcode_json, './debug/shortcode.json')
                new_html += '<table><tr><td><img src="{}" width="200px"/></td><td><strong>{}</strong><br/>'.format(resize_image(shortcode_json['imageGroup']['imageData']['path'], secret_key, 200), shortcode_json['hed'])
                if shortcode_json.get('offerPrice'):
                    new_html += '<div style="width:250px; padding:10px; margin-bottom:1em; background-color:red; text-align:center;"><a href="{}" style="color:white;">${:.2f} at {}</a></div>'.format(shortcode_json['offerUrl'], float(shortcode_json['offerPrice']), shortcode_json['offerMerchant'])
                elif shortcode_json.get('techProd') and shortcode_json['techProd'].get('resellers'):
                    promo_url = utils.get_redirect_url(shortcode_json['techProd']['resellers'][0]['url'])
                    new_html += '<div style="width:250px; padding:10px; margin-bottom:1em; background-color:red; text-align:center;"><a href="{}" style="color:white;">${:.2f} at {}</a></div>'.format(promo_url, int(shortcode_json['techProd']['resellers'][0]['price'])/100, shortcode_json['techProd']['resellers'][0]['name'])
                else:
                    new_html += '<div style="width:250px; padding:10px; margin-bottom:1em; background-color:red; text-align:center; color:white;"><a href="{}" style="color:white;"> View at {}</a></div>'.format(shortcode_json['offerUrl'], shortcode_json['offerMerchant'])
                new_html += '</td></tr></table>'

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
                    if re.search(r'https://joinsubtext\.com/|myFinance-widget', code):
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

        item['content_html'] += str(soup)
        if item['content_html'].endswith('<hr/>'):
            item['content_html'] = item['content_html'][:-5]
    return item


def get_feed(url, args, site_json, save_debug=False):
    if '/rss' in args['url'] or '/feed' in args['url']:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    # TODO: CNET tag feeds
    # TODO: CNET author feeds

    feed = None
    urls = []
    if args['url'].startswith('https://www.cnet.com/profiles/'):
        split_url = urlsplit(args['url'])
        paths = list(filter(None, split_url.path[1:].split('/')))
        api_url = 'https://www.cnet.com/profiles/user/profile/ugc/?username={}&type=recent&limit=10&offset=0&_={}'.format(paths[1], int(datetime.timestamp(datetime.now())*1000))
        headers = {
            "accept": "application/json, text/javascript, */*; q=0.01",
            "accept-language": "en-US,en;q=0.9,de;q=0.8",
            "sec-ch-ua": "\".Not/A)Brand\";v=\"99\", \"Microsoft Edge\";v=\"103\", \"Chromium\";v=\"103\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "x-requested-with": "XMLHttpRequest"
        }
        api_json = utils.get_url_json(api_url, headers=headers)
        if not api_json:
            return None
        soup = BeautifulSoup(api_json['html'], 'html.parser')
        if save_debug:
            utils.write_file(api_json, './debug/feed.json')
            utils.write_file(str(soup), './debug/debug.html')
        feed_title = 'CNET | ' + paths[1]
        for el in soup.find_all('h3'):
            if el.parent and el.parent.name == 'a':
                urls.append('https://www.cnet.com' + el.parent['href'])

    elif args['url'] == 'https://www.zdnet.com/pictures/':
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


def test_handler():
    feeds = ['https://www.zdnet.com/news/rss.xml',
             'https://www.zdnet.com/topic/reviews/rss.xml',
             'https://www.zdnet.com/videos/rss.xml',
             'https://www.zdnet.com/meet-the-team/palmsolo+%28aka+matthew+miller%29/rss.xml',
             'https://www.zdnet.com/pictures/',
             'https://www.cnet.com/rss/all/',
             'https://www.cnet.com/rss/reviews/',
             'https://feed.cnet.com/feed/roadshow/all',
             'https://www.tvguide.com/news/']
    for url in feeds:
        get_feed({"url": url}, True)
