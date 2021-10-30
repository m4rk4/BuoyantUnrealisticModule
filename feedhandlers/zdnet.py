import hashlib, hmac, json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

from feedhandlers import rss
import utils

import logging
logger = logging.getLogger(__name__)

def image_resize(img_src, width=1092):
  # https://www.zdnet.com/a/img/resize/8442e1cabace25833c896450c97727d73ee7477c/2021/10/25/83cabc85-3a18-484e-8d42-af9224d68e79/google-pixel-6-01.jpg?auto=webp&width=1200
  if img_src.startswith('https://www.zdnet.com/a/img/resize/'):
    m = re.search('\/resize\/[0-9a-f]+(\/[^\?]+)', img_src)
    if not m:
      logger.debug('unable to resize ' + img_src)
      return img_src
    path = m.group(1)
  elif img_src.startswith('https://image-resizer.prod.zdnet.com/i/'):
    path = urlsplit(img_src).path[2:]
  path += '?auto=webp&width={}'.format(width)
  # secret key from https://www.zdnet.com/a/neutron/953a029.modern.js
  key = 'nD869n2hThqkD9okFqNIfsMu2Zvrfp8OD/n7fJuVixI='
  digest = hmac.new(bytes(key, 'UTF-8'), bytes(path, 'UTF-8'), hashlib.sha1)
  return 'https://www.zdnet.com/a/img/resize/{}{}'.format(digest.hexdigest(), path)

def get_gallery_content(url, args, save_debug=False):
  # https://www.zdnet.com/pictures/first-look-16-inch-m1-pro-macbook-pro/
  m = re.search(r'\/pictures\/([^\/]+)', url)
  if not m:
    return None
  api_url = 'https://cmg-prod.apigee.net/v1/xapi/galleries/zdnet/{}/web?apiKey=hzY568JORMZcDzoFQ1ey5LBJuBS7DncX&componentName=gallery&componentDisplayName=Gallery&componentType=Gallery'.format(m.group(1))
  gallery_json = utils.get_url_json(api_url)
  if not gallery_json:
    return None
  if save_debug:
    utils.write_file(gallery_json, './debug/debug.json')

  item = {}
  item['id'] = gallery_json['data']['item']['id']
  item['url'] = url
  item['title'] = gallery_json['data']['item']['headline']

  dt = datetime.fromisoformat(gallery_json['data']['item']['datePublished']['date']).replace(tzinfo=timezone.utc)
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

  authors = []
  authors.append('{} {}'.format(gallery_json['data']['item']['author']['firstName'], gallery_json['data']['item']['author']['lastName']))
  if gallery_json['data']['item'].get('moreAuthors'):
    for author in gallery_json['data']['item']['moreAuthors']:
      authors.append('{} {}'.format(author['firstName'], author['lastName']))
  item['author'] = {}
  item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

  item['tags'] = []
  for tag in gallery_json['data']['item']['topics']:
    item['tags'].append(tag['name'])

  item['_image'] = gallery_json['data']['item']['promoImage']['path']

  item['content_html'] = ''
  if gallery_json['data']['item'].get('dek'):
    item['summary'] = gallery_json['data']['item']['dek']
    item['content_html'] += '<p><em>{}</em></p>'.format(gallery_json['data']['item']['dek'])

  n = len(gallery_json['data']['item']['items'])
  for i, gallery_item in enumerate(gallery_json['data']['item']['items']):
    caption = '{} of {} | '.format(i+1, n)
    if gallery_item.get('photoCredit'):
      caption += gallery_item['photoCredit']
    else:
      caption += '{}/ZDNet'.format(item['author']['name'])
    item['content_html'] += utils.add_image(image_resize(gallery_item['image']['path']), caption)
    if gallery_item.get('title'):
      item['content_html'] += '<h3>{}</h3>'.format(gallery_item['title'])
    if gallery_item.get('description'):
      item['content_html'] += gallery_item['description']
    item['content_html'] += '<hr style="width:80%" />'
  return item

def get_video_content(url, args, save_debug=False):
  video_html = utils.get_url_html(url)
  if not video_html:
    return None
  if save_debug:
    utils.write_file(video_html, './debug/debug.html')

  soup = BeautifulSoup(video_html, 'html.parser')

  for el in soup.find_all('script', attrs={"type": "application/ld+json"}):
    ld_json = json.loads(el.string)
    if ld_json['@type'] == 'VideoObject':
      break

  el = soup.find(attrs={"data-component":"videoPlaylistConnector"})
  video_playlist = json.loads(el['data-video-playlist-connector-options'])
  playlist = json.loads(video_playlist['playlist'])
  if save_debug:
    utils.write_file(playlist, './debug/playlist.json')
  video_json = playlist[0]

  item = {}
  item['id'] = video_json['id']
  item['url'] = url
  item['title'] = video_json['title']

  dt = datetime.fromisoformat(ld_json['uploadDate'].replace('Z', '+00:00'))
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

  item['author'] = {}
  item['author']['name'] = '{} {}'.format(video_json['author']['firstName'], video_json['author']['lastName'])

  item['summary'] = video_json['description']

  el = soup.find(class_='videoPlayer')
  video_options = json.loads(el['data-zdnet-video-options'])
  if save_debug:
    utils.write_file(video_options, './debug/video.json')
  video = video_options['videos'][0]
  item['_image'] = image_resize(video['previewImg'])
  if 'embed' in args:
    caption = item['summary']
  else:
    caption = ''
  if 'mp4' in video:
    item['_video'] = video['mp4']
    item['content_html'] = utils.add_video(video['mp4'], 'video/mp4', item['_image'], caption)
  elif 'm3u8' in video:
    item['_video'] = video['m3u8']
    item['content_html'] = utils.add_video(video['m3u8'], 'application/x-mpegURL', item['_image'], caption)
  if not 'embed' in args:
    item['content_html'] += '<p>{}</p>'.format(item['summary'])
  return item

def get_product_content(url, args, save_debug=False):
  article_html = utils.get_url_html(url)
  if not article_html:
    return None

  soup = BeautifulSoup(article_html, 'html.parser')
  for el in soup.find_all('script', attrs={"type": "application/ld+json"}):
    ld_json = json.loads(el.string)
    if ld_json.get('@type') == 'Product':
      break

  if save_debug:
    utils.write_file(ld_json, './debug/debug.json')

  item = {}
  m = re.search(r'"articleId":"([^"]+)"', article_html)
  if m:
    item['id'] = m.group(1)
  else:
    item['id'] = ld_json['review']['headline']
  item['url'] = url
  item['title'] = ld_json['review']['headline']

  dt = datetime.fromisoformat(ld_json['review']['datePublished']).replace(tzinfo=timezone.utc)
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
  dt = datetime.fromisoformat(ld_json['review']['dateModified']).replace(tzinfo=timezone.utc)
  item['date_modified'] = dt.isoformat()

  authors = []
  for author in ld_json['review']['author']:
    authors.append(author['name'])
  item['author'] = {}
  item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

  item['tags'] = [ld_json['category']]

  item['_image'] = ld_json['image']['url']
  item['summary'] = ld_json['review']['description']

  item['content_html'] = get_content_html(soup, item)

  if ld_json.get('additionalProperty'):
    item['content_html'] += '<h3>Specs</h3>'
    heading = ''
    for prop in ld_json['additionalProperty']:
      head, name = prop['name'].split(' - ')
      if head != heading:
        if item['content_html'][-5:] == '</li>':
          item['content_html'] += '</ul>'
        heading = head
        item['content_html'] += '<h4>{}</h4><ul>'.format(heading)
      item['content_html'] += '<li>{}: {}</li>'.format(name, ', '.join(prop['value']))
  return item

def get_content_html(soup, item):
  article_body = soup.find(class_='storyBody')
  if not article_body:
    return ''

  for el in article_body.find_all(['script', 'hr']):
    el.decompose()

  for el in article_body.find_all(class_=re.compile(r'listicle-precap|relatedContent|relatedReviews|sharethrough', flags=re.I)):
    el.decompose()

  for el in article_body.find_all('figure', class_='image'):
    img = el.find('img')
    if 'lazy' in img['class']:
      img_src = img['data-original']
    else:
      img_src = img['src']
    img_src = image_resize(img_src)
    caption = []
    it = el.find(class_='caption')
    if it:
      txt = it.get_text().strip()
      if txt:
        caption.append(txt)
    it = el.find(class_='credit')
    if it:
      txt = it.get_text().strip()
      if txt:
        caption.append(txt)
    new_el = BeautifulSoup(utils.add_image(img_src, ' | '.join(caption)), 'html.parser')
    el.insert_after(new_el)
    el.decompose()

  for el in article_body.find_all(class_='shortcodeGalleryWrapper'):
    split_url = urlsplit(item['url'])
    it = el.find('a', class_='full-gallery')
    gallery_url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, it['href'])
    gallery_item = get_gallery_content(gallery_url, {"embed": True})
    if gallery_item:
      new_el = BeautifulSoup('<hr/><h3><a href="{}">Gallery: {}</a></h3>{}'.format(gallery_url, gallery_item['title'], gallery_item['content_html']), 'html.parser')
      # Move galleries to end
      article_body.append(new_el)
      el.decompose()

  for el in article_body.find_all(class_='video'):
    player = el.find(class_='videoPlayer')
    if player:
      new_el = None
      video_options = json.loads(player['data-zdnet-video-options'])
      video = video_options['videos'][0]
      if 'mp4' in video:
        new_el = BeautifulSoup(utils.add_video(video['mp4'], 'video/mp4', video['previewImg'], video['title']), 'html.parser')
      elif 'm3u8' in video:
        new_el = BeautifulSoup(utils.add_video(video['m3u8'], 'application/x-mpegURL', video['previewImg'], video['title']), 'html.parser')
      if new_el:
        # Insert as lead if there's none
        has_lead = False
        for i in range(2):
          if article_body.contents[i].name and article_body.contents[i].name == 'figure':
            has_lead = True
        if not has_lead:
          article_body.insert(0, new_el)
        else:
          el.insert_after(new_el)
        el.decompose()

  for el in article_body.find_all(class_='shortcode'):
    if 'media-source' in el['class']:
      it = el.find('iframe')
      if it:
        new_el = BeautifulSoup(utils.add_embed(it['data-src']), 'html.parser')
        el.insert_after(new_el)
        el.decompose()
    elif not 'listicle' in el['class']:
      logger.warning('unhandled shortcode class {} in {}'.format(el['class'], item['url']))

  for el in article_body.find_all(class_='embed'):
    if 'embed--type-instagram' in el['class']:
      new_el = BeautifulSoup(utils.add_embed(el.blockquote['data-instgrm-permalink']), 'html.parser')
      el.insert_after(new_el)
      el.decompose()
    else:
      logger.warning('unhandled embed type {} in {}'.format(el['class'], item['url']))

  # Review rating + pros/cons
  for el in article_body.find_all(class_='row'):
    new_html = ''
    it = soup.find('span', class_='score')
    if it:
      new_html += '<div style="font-size:4em; margin:0; padding:0;">{}</div>'.format(it.get_text())
    it = soup.find('span', class_='ratingText')
    if it:
      new_html += '<div><em>{}</em></div>'.format(it.get_text())
    it = el.find('ul', class_='pros')
    if it:
      new_html += '<h4 style="margin-top:0.5; margin-bottom:0.5em;">Pros</h4><ul style="margin-top:0;">'
      for li in it.find_all('li'):
        if li.span:
          li.span.decompose()
        new_html += '<li>{}</li>'.format(li.get_text())
      new_html += '</ul>'
    it = el.find('ul', class_='cons')
    if it:
      new_html += '<h4 style="margin-top:0.5; margin-bottom:0.5em;">Cons</h4><ul style="margin-top:0;">'
      for li in it.find_all('li'):
        if li.span:
          li.span.decompose()
        new_html += '<li>{}</li>'.format(li.get_text())
      new_html += '</ul>'
    if new_html:
      new_html += '<hr style="width:80%;" />'
      el.insert_after(BeautifulSoup(new_html, 'html.parser'))
      el.decompose()

  # Review card
  for el in article_body.find_all(class_='review-card'):
    new_html = ''
    it = el.find(class_='rating-number')
    if it:
      new_html += '<div style="font-size:4em; margin:0; padding:0;">{}</div>'.format(it.get_text())
    it = el.find(class_='product-score')
    if it:
      new_html += '<div><em>{}</em></div>'.format(it.get_text())
    it = el.find('ul', class_='review-card-likes')
    if it:
      new_html += '<h4 style="margin-top:0.5; margin-bottom:0.5em;">{}</h4><ul style="margin-top:0;">'.format(el.find(class_='review-card-likes-heading').get_text())
      for li in it.find_all(class_='review-card-list-text'):
        new_html += '<li>{}</li>'.format(li.get_text())
      new_html += '</ul>'
    it = el.find('ul', class_='review-card-dislikes')
    if it:
      new_html += '<h4 style="margin-top:0.5; margin-bottom:0.5em;">{}</h4><ul style="margin-top:0;">'.format(el.find(class_='review-card-dislikes-heading').get_text())
      for li in it.find_all(class_='review-card-list-text'):
        new_html += '<li>{}</li>'.format(li.get_text())
      new_html += '</ul>'
    it = el.find(class_='review-card-buttons')
    for link in it.find_all('a'):
      new_html += '<a href="{}">{}</a>'.format(utils.get_redirect_url(link['href']), link.get_text())
    new_html += '<hr style="width:80%;" />'
    el.insert_after(BeautifulSoup(new_html, 'html.parser'))
    el.decompose()

  for el in article_body.find_all(class_='listicle'):
    new_listicle = ''
    for it in el.find_all(True, recursive=False):
      if it.name == 'h2' or it.name == 'h3':
        new_listicle += '<{0}>{1}</{0}>'.format(it.name, it.get_text().strip())
      elif it.name == 'a' or (it.get('class') and 'imageContainer' in it.get('class')):
        img = it.find('img')
        if img:
          if 'lazy' in img['class']:
            img_src = img['data-original']
          else:
            img_src = img['src']
          new_listicle += utils.add_image(img_src)
        else:
          new_listicle += '<a href="{}">{}</a><br />'.format(utils.get_redirect_url(it['href']), it.get_text().strip())
      else:
        new_listicle += str(it)
    el.insert_after(BeautifulSoup(new_listicle, 'html.parser'))
    el.decompose()

  for el in article_body.find_all(class_='lead-link'):
    new_link = '<a href="{}">{}</a>'.format(utils.get_redirect_url(el['href']), el.get_text().strip())
    if el.parent.has_attr('class') and 'listicle-links' in el.parent['class']:
      el.parent.attrs.clear()
    el.insert_after(BeautifulSoup(new_link, 'html.parser'))
    el.decompose()

  for el in article_body.find_all(attrs={"data-shortcode": True}):
    el.decompose()

  for el in article_body.find_all(['p','h3']):
    try:
      if el.strong and re.search(r'^(Also:|Must read:|SEE:|See also:)', el.strong.get_text()):
        el.decompose()
      elif el.strong and re.search(r'^(RECENT AND RELATED CONTENT)', el.strong.string):
        while ((el.next_sibling.a and el.next_sibling.a.strong) or (el.next_sibling.strong and el.next_sibling.strong.a)):
          el.next_sibling.decompose()
        el.decompose()
      elif re.search(r'^(Related Stories|Related Coverage|Read more reviews)', el.get_text(), flags=re.I):
        if el.next_sibling.name == 'ul':
          el.next_sibling.decompose()
          el.decompose()
    except Exception as e:
      logger.warning('zdnet exception: ' + str(e))
      pass

  # Add a lead image if one is not present
  has_lead = False
  for i in range(2):
    if article_body.contents[i].name and article_body.contents[i].name == 'figure':
      has_lead = True
  if not has_lead:
    if item.get('_image'):
      article_body.insert(0, BeautifulSoup(utils.add_image(item['_image']), 'html.parser'))

  return article_body.decode_contents().replace('\n', '')

def get_content(url, args, save_debug=False):
  clean_url = utils.clean_url(url)
  if '/product/' in clean_url:
    return get_product_content(url, args, save_debug)
  elif '/pictures/' in clean_url:
    return get_gallery_content(url, args, save_debug)
  elif '/video/' in clean_url:
    return get_video_content(url, args, save_debug)

  if not clean_url.endswith('/'):
    clean_url += '/'
  article_xhr = utils.get_url_json(clean_url + 'xhr/')
  if not article_xhr:
    return None
  if save_debug:
    utils.write_file(article_xhr, './debug/debug.json')

  soup = BeautifulSoup(article_xhr['template'], 'html.parser')

  item = {}
  item['id'] = article_xhr['trackingData']['articleId']
  item['url'] = clean_url
  item['title'] = article_xhr['trackingData']['articleTitle'].title()

  dt = datetime.fromisoformat(article_xhr['trackingData']['articlePubDate']).replace(tzinfo=timezone.utc)
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

  authors = []
  for author in article_xhr['trackingData']['articleAuthorName']:
    authors.append(author.title())
  if authors:
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

  item['tags'] = article_xhr['trackingData']['topicName'].copy()

  el = soup.find('meta', attrs={"property":"og:image"})
  if el:
    item['_image'] = el['content']

  el = soup.find('meta', attrs={"property":"og:description"})
  if el:
    item['summary'] = el['content']

  item['content_html'] = get_content_html(soup, item)
  return item

def get_feed(args, save_debug=False):
  return rss.get_feed(args, save_debug, get_content)