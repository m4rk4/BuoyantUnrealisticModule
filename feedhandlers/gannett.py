import json, math, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import utils

import logging
logger = logging.getLogger(__name__)

def resize_image(img_src, width=1000):
  img_src = re.sub(r'(\?|&)(height=\d+)', '', img_src)
  m = re.search('(\?|&)(width=\d+)', img_src)
  if m:
    img_src = img_src.replace(m.group(2), 'width={}'.format(width))
  else:
    if '?' in img_src:
      img_src += '&width={}'.format(width)
    else:
      img_src += '?width={}'.format(width)
  return img_src

def get_image(el):
  if el.name == 'img':
    img = el_img
  else:
    el_img = el.find('img')
  if not el_img:
    return '', ''

  img_src = ''
  if el_img.has_attr('src'):
    img_src = el_img['src']
  elif el_img.has_attr('data-gl-src'):
    img_src = el_img['data-gl-src']
  img_src = resize_image(img_src)

  caption = []
  it = el.find(attrs={"data-c-caption": True})
  if it:
    if it['data-c-caption']:
      caption.append(it['data-c-caption'])
  it = el.find(attrs={"data-c-credit": True})
  if it:
    if it['data-c-credit']:
      caption.append(it['data-c-credit'])

  return img_src, ' | '.join(caption)

def get_gallery_content(gallery_soup):
  gallery_html = ''
  for slide in gallery_soup.find_all('slide'):
    img_src = resize_image(slide['original'])
    caption = []
    if slide.get('caption'):
      cap = slide['caption'].replace('&nbsp;', ' ').strip()
      if cap.endswith('<br />'):
        cap = cap[:-6].strip()
      caption.append(cap)
    if slide.get('author'):
      caption.append(slide['author'])
    gallery_html += utils.add_image(img_src, ' | '.join(caption))
  return gallery_html

def get_video_content(url, args, save_debug=False):
  item = None
  video_html = utils.get_url_html(url)
  soup = BeautifulSoup(video_html, 'html.parser')
  el = soup.find('button', class_='gnt_em_vp_a')

  if el and el.has_attr('data-c-vpdata'):
    info = json.loads(el.get('data-c-vpdata'))
    if save_debug:
      utils.write_file(info, './debug/debug.json')

    item = {}
    item['url'] = url
    item['id'] = url
    item['title'] = info['headline']

    item['author'] = {}
    item['author']['name'] = info['credit']

    dt = datetime.fromisoformat(info['publishDate'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

    item['tags'] = []
    for tag in info['tags']:
      item['tags'].append(tag['name'])

    poster = resize_image(info['image']['url'])
    video = soup.find('video')
    if video and video.has_attr('poster'):
      print(video['poster'])
      width = -1
      height = -1
      m = re.search(r'width=(\d+)', video['poster'])
      if m:
        width = int(m.group(1))
      m = re.search(r'height=(\d+)', video['poster'])
      if m:
        height = int(m.group(1))
      if width > 0 and height > 0:
        w = 1080
        h = (height * w) // width
        poster = video['poster'].replace('width={}'.format(width), 'width={}'.format(w))
        poster = poster.replace('height={}'.format(height), 'height={}'.format(h))
    item['_image'] = poster
    item['_video'] = info['mp4URL']
    item['summary'] = info['promoBrief']

    item['content_html'] = utils.add_video(info['mp4URL'], 'video/mp4', poster)
    item['content_html'] += '<p>{}</p>'.format(info['promoBrief'])
  return item

def get_content(url, args, save_debug=False):
  split_url = urlsplit(args['url'])
  base_url = split_url.scheme + '://' + split_url.netloc

  if '/videos/' in url:
    return get_video_content(url, args, save_debug)

  article_html = utils.get_url_html(url)
  if save_debug:
    utils.write_file(article_html, './debug/debug.html')

  item = {}
  item['url'] = url
  item['id'] = url

  soup = BeautifulSoup(article_html, 'html.parser')
  el = soup.find('script', attrs={"type": "application/ld+json"})
  if el:
    ld_json = json.loads(el.string)
    if isinstance(ld_json, list):
      info = ld_json[0]
    else:
      info = ld_json
    if save_debug:
      utils.write_file(info, './debug/debug.json')

    item['title'] = info['headline']

    if isinstance(info['author'], list):
      authors = []
      for author in info['author']:
        if isinstance(author, dict):
          authors.append(author['name'])
        else:
          authors.append(author)
      author = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    elif isinstance(info['author'], dict):
      author = info['author']['name']
    else:
      author = info['author']
    if 'publisher' in info:
      if info['publisher']['name'] != author:
        author += ', {}'.format(info['publisher']['name'])
    item['author'] = {}
    item['author']['name'] = author

    dt = datetime.fromisoformat(info['datePublished'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
    dt = datetime.fromisoformat(info['dateModified'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    if info.get('keywords'):
      item['tags'] = []
      for tag in info['keywords']:
        if 'tag:' in tag:
          item['tags'].append(tag.split(':')[1])

    if info.get('image'):
      item['_image'] = resize_image(info['image']['url'])
    elif 'thumbnailUrl' in info:
      item['_image'] = resize_image(info['thumbnailUrl'])

    if info.get('description'):
      item['summary'] = info['description']
  else:
    el = soup.find('meta', attrs={"property": "og:title"})
    if el:
      item['title'] = el['content']

    item['author'] = {}
    el = soup.find('meta', attrs={"property": "article:author"})
    if el:
      item['author']['name'] = el['content']
    else:
      el = soup.find('div', class_='gnt_ar_pb')
      if el:
        item['author']['name'] = el.get_text()

    el = soup.find('meta', attrs={"name": "description"})
    if el:
      item['summary'] = el['content']

    el = soup.find(class_='gnt_ar_dt')
    if el:
      pub_time = el['aria-label']
      m = re.search(r'Published:?\s(\d{1,2}):(\d{2})\s([ap])\.m\.\s([A-Z]{2,3})\s([a-zA-Z]{3})\.\s(\d{1,2}),\s(202\d)', pub_time)
      if m:
        dt = None
        dt_str = '{}:{} {}M {} {} {}'.format(m.group(1).zfill(2), m.group(2), m.group(3).upper(), m.group(5), m.group(6).zfill(2), m.group(7))
        dt_loc = datetime.strptime(dt_str, '%I:%M %p %b %d %Y')
        if m.group(4) == 'ET':
          dt_loc = pytz.timezone('US/Eastern').localize(dt_loc)
          dt = dt_loc.astimezone(pytz.timezone('UTC'))
        else:
          dt = pytz.timezone('UTC').localize(dt_loc)
        if dt:
          item['date_published'] = dt.isoformat()
          item['_timestamp'] = dt.timestamp()
          item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

      m = re.search(r'Updated:?\s(\d{1,2}):(\d{2})\s([ap])\.m\.\s([A-Z]{2,3})\s([a-zA-Z]{3})\.\s(\d{1,2}),\s(202\d)', pub_time)
      if m:
        dt = None
        dt_str = '{}:{} {}M {} {} {}'.format(m.group(1).zfill(2), m.group(2), m.group(3).upper(), m.group(5), m.group(6).zfill(2), m.group(7))
        dt_loc = datetime.strptime(dt_str, '%I:%M %p %b %d %Y')
        if m.group(4) == 'ET':
          dt_loc = pytz.timezone('US/Eastern').localize(dt_loc)
          dt = dt_loc.astimezone(pytz.timezone('UTC'))
        else:
          dt = pytz.timezone('UTC').localize(dt_loc)
        if dt:
          item['date_modified'] = dt.isoformat()

  # Photo galleries
  if '/picture-gallery/' in url:
    item['content_html'] = get_gallery_content(soup)
    return item

  # News articles
  article = soup.find(class_='gnt_ar_b')
  if not article:
    logger.warning('unable to parse article contents in ' + url)
    return item

  # Ads
  for el in article.find_all(attrs={"aria-label": "advertisement"}):
    el.decompose()

  # Images
  for el in article.find_all('figure'):
    img_src, caption = get_image(el)
    new_el = BeautifulSoup(utils.add_image(img_src, caption), 'html.parser')
    el.insert_after(new_el)
    el.decompose()

  # Gallery
  for el in article.find_all('a', class_='gnt_em_gl'):
    gallery_url = base_url + el['href']

    # Add the ref image in place and append the full gallery to the end of the article
    img_src, caption = get_image(el)
    if img_src:
      if caption:
        caption = '<a href="">{}</a>'.format(gallery_url)
      else:
        caption = '<a href="{}">{}</a>'.format(gallery_url, el['aria-label'])
      new_el = BeautifulSoup(utils.add_image(img_src, caption), 'html.parser')
      el.insert_after(new_el)

    new_html = '<h3><a href="{}">{}</a></h3>'.format(gallery_url, el['aria-label'])

    gallery_html = utils.get_url_html(gallery_url)
    if gallery_html:
      new_html += get_gallery_content(BeautifulSoup(gallery_html, 'html.parser'))
    new_el = BeautifulSoup(new_html, 'html.parser')
    article.append(new_el)
    el.decompose()

  # Lead image
  el = soup.find(class_='gnt_em__fp')
  if el:
    new_el = None
    if el.name == 'figure':
      img_src, caption = get_image(el)
      new_el = BeautifulSoup(utils.add_image(img_src, caption), 'html.parser')
    elif el.name == 'aside' and el.button:
      if el.button.has_attr('data-c-vpdata'):
        video_json = json.loads(el.button['data-c-vpdata'])
        if video_json:
          video_url = video_json['url']
          if video_url.startswith('/'):
            video_url = base_url + video_url
          video = get_video_content(video_url, {}, save_debug)
          if video:
            new_el = BeautifulSoup(utils.add_video(video['_video'], 'video/mp4', video['_image'], video['summary']), 'html.parser')
    if new_el:
      article.insert(0, new_el)
      el.decompose()

  # Pullquote
  for el in article.find_all(class_='gnt_em_pq'):
    new_el = BeautifulSoup(utils.add_pullquote(el['data-c-pq'], el['data-c-cr']), 'html.parser')
    el.insert_after(new_el)
    el.decompose()

  # These are usually ads
  for el in article.find_all('aside'):
    el.decompose()

  # Fix local href links
  for el in article.find_all('a'):
    if el.has_attr('href'):
      href = el.get('href')
    if not href.startswith('http'):
      href = base_url + href
    el.attrs = {}
    el['href'] = utils.clean_referral_link(href)

  # Clear remaining attrs
  article.attrs = {}
  for el in article.find_all(re.compile(r'\b(h\d|li|ol|p|span|ul)\b'), class_=True):
    el.attrs = {}

  item['content_html'] = str(article)
  return item

def get_feed(args, save_debug=False):
  split_url = urlsplit(args['url'])
  base_url = split_url.scheme + '://' + split_url.netloc

  # Get a list of article urls from the past 2 days from the sitemap page
  stories = []
  for n in reversed(range(2)):
    dt = datetime.utcnow().date() - timedelta(days=n)
    url = base_url + '/sitemap/' + dt.strftime('%Y/%B/%d/')
    html = utils.get_url_html(url)
    soup = BeautifulSoup(html, 'html.parser')
    for a in soup.find_all('a'):
      if a.has_attr('href'):
        if '/story/' in a.get('href') or '/videos/' in a.get('href') or '/picture-gallery/' in a.get('href'):
          stories.append(a.get('href'))

  old = 0
  max_old = 3
  items = []
  # Loop in reverse order then order should be newest to oldest
  for url in reversed(stories):
    if save_debug:
      logger.debug('getting content for ' + url)
    item = get_content(url, args, save_debug)
    # Check age
    if utils.check_age(item, args) == False:
      old += 1
    # Check other filters (rechecks age)
    if utils.filter_item(item, args) == True:
      items.append(item)
    # Stop if there are several old articles
    if old == max_old:
      break

  # Create feed and add items sorted by date
  feed = utils.init_jsonfeed(args)
  del feed['items']
  feed['items'] = sorted(items, key=lambda i: i['_timestamp'], reverse=True).copy()
  return feed