import json, math, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import utils

import logging
logger = logging.getLogger(__name__)

def resize_image(img_src, width=800):
  def resize_image_sub(matchobj):
    nonlocal width
    w = width
    h = math.ceil(800*int(matchobj.group(2))/int(matchobj.group(1)))
    return 'width={}&height={}'.format(w, h)
  return re.sub('width=(\d+)&height=(\d+)', resize_image_sub, img_src)

def get_gallery_content(url, args, save_debug=False):
  item = None
  html = utils.get_url_html(url)
  soup = BeautifulSoup(html, 'html.parser')
  el = soup.find('script', attrs={"type": "application/ld+json"})
  if el:
    ld_json = json.loads(el.string)
    if isinstance(ld_json, list):
      info = ld_json[0]
    else:
      info = ld_json
    if save_debug:
      with open('./debug/debug.json', 'w') as file:
        json.dump(info, file, indent=4)

    item = {}
    item['url'] = url
    item['id'] = url
    item['title'] = info['headline']
    if 'author' in info:
      item['author'] = {}
      item['author']['name'] = info['author']['name']
    else:
      item['author'] = {}
      item['author']['name'] = info['soureOrganization']['name']
    dt = datetime.fromisoformat(info['datePublished'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt_pub.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
    if info.get('dateModified'):
      dt = datetime.fromisoformat(info['dateModified'].replace('Z', '+00:00'))
      item['date_modified'] = dt.isoformat()

    if 'keywords' in info:
      item['tags'] = []
      for tag in info['keywords']:
        if 'tag:' in tag:
          item['tags'].append(tag.split(':')[1])
    else:
      item['tags'] = []
      item['tags'].append(info['primaryTag']['name'])
    item['_image'] = info['image']['url']
    if 'promoBrief' in info:
      item['summary'] = info['promoBrief']

    el = soup.find('media-gallery-vertical')
    if el:
      content = ''
      slides = el.find_all('slide')
      n = 1
      n_slides = len(slides)
      for slide in slides:
        width = 800
        img_src = slide.get('original')
        if '?' in img_src:
          img_src += '&width=800'
        else:
          img_src += '?width=800'
        caption = '[{}/{}] {} ({})'.format(n, n_slides, slide.get('caption'), slide.get('author'))
        content += utils.add_image(img_src, caption)
        n += 1
      item['content_html'] = content
  return item

def get_video_content(url, args, save_debug=False):
  item = None
  html = utils.get_url_html(url)
  soup = BeautifulSoup(html, 'html.parser')
  el = soup.find('button', class_='gnt_em_vp_a')
  if el and el.has_attr('data-c-vpdata'):
    info = json.loads(el.get('data-c-vpdata'))
    if save_debug:
      with open('./debug/debug.json', 'w') as file:
        json.dump(info, file, indent=4)

    item = {}
    item['url'] = url
    item['id'] = url
    item['title'] = info['headline']
    item['author'] = {}
    item['author']['name'] = info['credit']
    dt_pub = datetime.fromisoformat(info['publishDate'].replace('Z', '+00:00'))
    item['date_published'] = dt_pub.isoformat()
    item['_timestamp'] = dt_pub.timestamp()
    item['_display_date'] = dt_pub.strftime('%b. %-d, %Y')
    item['tags'] = []
    for tag in info['tags']:
      item['tags'].append(tag['name'])
    item['_image'] = info['image']['url']
    item['summary'] = info['promoBrief']
    item['content_html'] = utils.add_video(info['mp4URL'], 'video/mp4', info['image']['url'])
    item['content_html'] += '<p>{}</p>'.format(info['promoBrief'])
  return item

def get_content(url, args, save_debug=False):
  if '/videos/' in url:
    return get_video_content(url, args, save_debug)
  elif '/picture-gallery/' in url:
    return get_gallery_content(url, args, save_debug)

  html = utils.get_url_html(url)
  soup = BeautifulSoup(html, 'html.parser')
  el = soup.find('script', attrs={"type": "application/ld+json"})
  if el:
    ld_json = json.loads(el.string)
    if isinstance(ld_json, list):
      info = ld_json[0]
    else:
      info = ld_json
    if save_debug:
      with open('./debug/debug.json', 'w') as file:
        json.dump(info, file, indent=4)

    headline = info['headline']
    if isinstance(info['author'], list):
      author = info['author'][0]
    else:
      author = info['author']
    if 'publisher' in info:
      if info['publisher']['name'] != author:
        author += ', {}'.format(info['publisher']['name'])
    dt_pub = datetime.fromisoformat(info['datePublished'].replace('Z', '+00:00'))
    dt_mod = datetime.fromisoformat(info['dateModified'].replace('Z', '+00:00'))
    tags = []
    for tag in info['keywords']:
      if 'tag:' in tag:
        tags.append(tag.split(':')[1])
    if 'image' in info:
      image = resize_image(info['image']['url'])
    elif 'thumbnailUrl' in info:
      image = resize_image(info['thumbnailUrl'])
    else:
      image = None
    summary = info['description']
  else:
    el = soup.find('meta', attrs={"property": "og:title"})
    if el:
      headline = el['content']
    el = soup.find('meta', attrs={"property": "article:author"})
    if el:
      author = el['content']
    else:
      el = soup.find('div', class_='gnt_ar_pb')
      if el:
        author = el.get_text()
    el = soup.find('meta', attrs={"name": "description"})
    if el:
      summary = el['content']
    el = soup.find(class_='gnt_ar_dt')
    if el:
      pub_time = el['aria-label']
      m = re.search(r'Published:?\s(\d{1,2}):(\d{2})\s([ap])\.m\.\s([A-Z]{2,3})\s([a-zA-Z]{3})\.\s(\d{1,2}),\s(202\d)', pub_time)
      if m:
        dt_str = '{}:{} {}M {} {} {}'.format(m.group(1).zfill(2), m.group(2), m.group(3).upper(), m.group(5), m.group(6).zfill(2), m.group(7))
        dt_loc = datetime.strptime(dt_str, '%I:%M %p %b %d %Y')
        if m.group(4) == 'ET':
          dt_loc = pytz.timezone('US/Eastern').localize(dt_loc)
          dt_pub = dt_loc.astimezone(pytz.timezone('UTC'))
        else:
          dt_pub = pytz.timezone('UTC').localize(dt_loc)
      else:
        dt_pub = None
      m = re.search(r'Updated:?\s(\d{1,2}):(\d{2})\s([ap])\.m\.\s([A-Z]{2,3})\s([a-zA-Z]{3})\.\s(\d{1,2}),\s(202\d)', pub_time)
      if m:
        dt_str = '{}:{} {}M {} {} {}'.format(m.group(1).zfill(2), m.group(2), m.group(3).upper(), m.group(5), m.group(6).zfill(2), m.group(7))
        dt_loc = datetime.strptime(dt_str, '%I:%M %p %b %d %Y')
        if m.group(4) == 'ET':
          dt_loc = pytz.timezone('US/Eastern').localize(dt_loc)
          dt_mod = dt_loc.astimezone(pytz.timezone('UTC'))
        else:
          dt_mod = pytz.timezone('UTC').localize(dt_loc)
      else:
        dt_mod = None
    else:
      dt_pub = None
      dt_mod = None
    tags = None

  item = {}
  item['url'] = url
  item['id'] = url
  item['title'] = headline
  if author:
    item['author'] = {}
    item['author']['name'] = author
  if dt_pub:
    item['date_published'] = dt_pub.isoformat()
    item['_timestamp'] = dt_pub.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt_pub.strftime('%b'), dt_pub.day, dt_pub.year)
  if dt_mod:
    item['date_modified'] = dt_mod.isoformat()
    item['_timestamp'] = dt_mod.timestamp()
  if tags:
    item['tags'] = tags.copy()
  if image:
    item['image'] = image
  item['summary'] = summary

  # Parse the main story contents
  contents = soup.find(class_='gnt_ar_b')

  # Remove asides - usually ads and related content
  for el in contents.find_all('aside'):
    el.decompose()

  # Fix local href links
  split_url = urlsplit(args['url'])
  base_url = split_url.scheme + '://' + split_url.netloc
  for el in contents.find_all('a'):
    if el.has_attr('href'):
      if not el.get('href').startswith('http'):
        el['href'] = base_url + el.get('href')

  # Reformat figures/images
  for el in contents.find_all('figure'):
    img = el.find('img')
    if img:
      # Remove the feed image if there's a lead image (for Inoreader)
      if img.has_attr('elementtiming') and 'lead-image' in img.get('elementtiming'):
        if item.get('image'):
          item['_image'] = item['image']
          del item['image']

      img_src = ''
      if img.has_attr('src'):
        img_src = img.get('src')
      elif img.has_attr('data-gl-src'):
        img_src = img.get('data-gl-src')
      elif img.has_attr('srcset'):
        img_src = img.get('srcset').split(' ')[0]
      elif img.has_attr('data-gl-srcset'):
        img_src = img.get('data-gl-srcset').split(' ')[0]
      img_src = resize_image(img_src)    

      caption = ''
      cap = el.find(class_='gnt_em_img_ccw')
      if cap:
        if cap.has_attr('data-c-caption'):
          caption += cap.get('data-c-caption')
        if cap.has_attr('data-c-credit'):
          caption += ' <i>{}</i>'.format(cap.get('data-c-credit'))

      if img_src:
        new_el = BeautifulSoup(utils.add_image(img_src, caption), 'html.parser')
        el.insert_after(new_el)
        el.decompose()

  # Reformat galleries
  for el in contents.find_all('a', class_='gnt_em'):
    if el.has_attr('data-t-l') and 'Gallery' in el.get('data-t-l'):
      img = el.find('img')
      if img:
        # Remove the feed image if there's a lead image (for Inoreader)
        if img.has_attr('elementtiming') and 'lead-image' in img.get('elementtiming'):
          if item.get('image'):
            item['_image'] = item['image']
            del item['image']

        img_src = ''
        if img.has_attr('src'):
          img_src = img.get('src')
        elif img.has_attr('data-gl-src'):
          img_src = img.get('data-gl-src')
        elif img.has_attr('srcset'):
          img_src = img.get('srcset').split(' ')[0]
        elif img.has_attr('data-gl-srcset'):
          img_src = img.get('data-gl-srcset').split(' ')[0]
        img_src = resize_image(img_src)

        caption = ''
        cap = el.find(class_='gnt_em_t')
        if cap:
          if cap.has_attr('data-c-et'):
            caption += '<a href="{}"><b>{}</b></a>'.format(el.get('href'), cap.get('data-c-et'))
          if cap.has_attr('aria-label'):
            if len(caption) > 0:
              caption += '<br />'
            caption += cap.get('aria-label')
        if len(caption) > 0:
          caption += ' | '
        caption += '<a href="{}">View Gallery</a>'.format(el.get('href'))

        if img_src:
          new_el = BeautifulSoup(utils.add_image(img_src, caption), 'html.parser')
          el.insert_after(new_el)
          el.decompose()

  item['content_html'] = str(contents)
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
    if False:
      with open('./debug/debug.html', 'w', encoding='utf-8') as f:
        f.write(html)

    soup = BeautifulSoup(html, 'html.parser')
    for a in soup.find_all('a'):
      if a.has_attr('href'):
        if '/story/' in a.get('href') or '/videos/' in a.get('href') or '/picture-gallery/' in a.get('href'):
          stories.append(a.get('href'))

  # Remove duplicates
  #stories = list(OrderedDict.fromkeys(stories))

  num_old = 0
  items = []
  # Loop in reverse order then order should be newest to oldest
  for url in reversed(stories):
      item = get_content(url, args, save_debug)
      # Check age
      if utils.check_age(item, args) == False:
        num_old += 1
      # Check other filters (rechecks age)
      if utils.filter_item(item, args) == True:
        items.append(item)
      # Stop if there are several old articles
      if num_old == 3:
        break

  # Create feed and add items sorted by date
  feed = utils.init_jsonfeed(args)
  del feed['items']
  feed['items'] = sorted(items, key=lambda i: i['_timestamp'], reverse=True).copy()
  return feed