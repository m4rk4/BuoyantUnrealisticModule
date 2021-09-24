import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import unquote_plus

from feedhandlers import rss
import utils

import logging
logger = logging.getLogger(__name__)

def get_full_image(img_src):
  m = re.search(r'(https:\/\/s\.yimg\.com\/os\/creatr-uploaded-images\/[^\.]+)', img_src)
  if m:
    return m.group(1)
  m = re.search(r'image_uri=([^&]+)', img_src)
  if m:
    return unquote_plus(m.group(1))
  return img_src

def get_image(image_wrapper):
  img = image_wrapper.find('img')
  if not img:
    return ''
  if img.get('src'):
    img_src = img['src']
  elif img.get('data-src'):
    img_src = img['data-src']
  else:
    logger.warning('unknown img src in ' + str(img))
    return ''
  caption = ''
  if img.get('alt'):
    caption = img['alt']
  else:
    figcap = image_wrapper.find('figcaption')
    if figcap:
      caption = figcap.get_text()
  return utils.add_image(get_full_image(img_src), caption)

def get_video(video_wrapper):
  yvideo = video_wrapper.find(class_='caas-yvideo')
  if not yvideo:
    return ''
  video_config = json.loads(yvideo['data-videoconfig'])
  if video_config.get('media_id_1'):
    video_id = video_config['media_id_1']
  elif video_config.get('playlist'):
    video_id = video_config['playlist']['mediaItems'][0]['id']
  else:
    logger.warning('unknown video id in ' + str(yvideo))
    return ''
  video_json = utils.get_url_json('https://video-api.yql.yahoo.com/v1/video/sapi/streams/{}?protocol=http&format=mp4,webm,m3u8'.format(video_id))
  if not video_json:
    return ''
  utils.write_file(video_json, './debug/video.json')
  video = utils.closest_dict(video_json['query']['results']['mediaObj'][0]['streams'], 'height', 360)
  caption = []
  if video_json['query']['results']['mediaObj'][0]['meta'].get('title'):
    caption.append(video_json['query']['results']['mediaObj'][0]['meta']['title'])
  if video_json['query']['results']['mediaObj'][0]['meta'].get('attribution'):
    caption.append(video_json['query']['results']['mediaObj'][0]['meta']['attribution'])
  poster = video_json['query']['results']['mediaObj'][0]['meta']['thumbnail']
  return utils.add_video(video['host'] + video['path'], video['mime_type'], poster, ' | '.join(caption))

def get_iframe(iframe_wrapper):
  embed = iframe_wrapper.find('iframe')
  if not embed:
    embed = iframe_wrapper.find('blockquote')
  embed_src = ''
  if embed.get('src'):
    embed_src = embed['src']
  elif embed.get('data-src'):
    embed_src = embed['data-src']
  if not embed_src:
    return ''
  return utils.add_embed(embed_src)

def get_content(url, args, save_debug=False):
  # Need to load the article page first to set appropriate cookies otherwise some embedded content is restricted
  s = utils.requests_retry_session()
  headers = {"accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
             "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.54 Safari/537.36",
             "sec-ch-ua": "\"Chromium\";v=\"94\", \"Google Chrome\";v=\"94\", \";Not A Brand\";v=\"99\""}
  r = s.get(url, headers=headers)
  if r.status_code != 200:
    return None

  #article_html = utils.get_url_html(url, 'desktop')
  #if not article_html:
  #  return None
  article_html = r.text
  if save_debug:
    utils.write_file(article_html, './debug/debug.html')

  m = re.search(r'"pstaid":"([^"]+)"', article_html)
  if not m:
    logger.warning('unable to find post-id in ' + url)
    return None

  article_soup = BeautifulSoup(article_html, 'html.parser')

  post_id = m.group(1)
  caas_url = 'https://www.yahoo.com/caas/content/article/?uuid=' + post_id
  #caas_json = utils.get_url_json(caas_url)
  r = s.get(caas_url)
  if r.status_code != 200:
    return None

  caas_json = r.json()
  if not caas_json:
    return None
  if save_debug:
    utils.write_file(caas_json, './debug/debug.json')

  article_json = caas_json['items'][0]['schema']['default']
  item = {}
  item['id'] = post_id
  item['url'] = article_json['mainEntityOfPage']
  item['title'] = article_json['headline']

  dt = datetime.fromisoformat(article_json['datePublished'].replace('Z', '+00:00'))
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
  dt = datetime.fromisoformat(article_json['dateModified'].replace('Z', '+00:00'))
  item['date_modified'] = dt.isoformat()

  item['author'] = {}
  item['author']['name'] = article_json['author']['name']

  item['tags'] = article_json['keywords'].copy()

  item['_image'] = article_json['image']['url']

  item['summary'] = article_json['description']

  #if save_debug:
  #  utils.write_file(caas_json['items'][0]['markup'], './debug/debug.html')

  caas_soup = BeautifulSoup(caas_json['items'][0]['markup'], 'html.parser')
  caas_body = caas_soup.find(class_='caas-body')

  for el in caas_body.find_all('figure'):
    new_html = get_image(el)
    if new_html:
      el.insert_after(BeautifulSoup(new_html, 'html.parser'))
      el.decompose()

  for el in caas_body.find_all(class_='caas-carousel'):
    new_html = ''
    for slide in el.find_all(class_='caas-carousel-slide'):
      new_html += get_image(slide)
    if new_html:
      el.insert_after(BeautifulSoup(new_html, 'html.parser'))
      el.decompose()

  for el in caas_body.find_all(class_='caas-yvideo-wrapper'):
    new_html = get_video(el)
    if new_html:
      el.insert_after(BeautifulSoup(new_html, 'html.parser'))
      el.decompose()

  for el in caas_body.find_all(class_='caas-iframe-wrapper'):
    new_html = get_iframe(el)
    if new_html:
      el.insert_after(BeautifulSoup(new_html, 'html.parser'))
      el.decompose()

  for el in caas_body.find_all(class_='caas-iframe'):
    new_html = get_iframe(el)
    if new_html:
      el.insert_after(BeautifulSoup(new_html, 'html.parser'))
      el.decompose()

  for el in caas_body.find_all(class_='twitter-tweet-wrapper'):
    tweet_urls = el.find_all('a')
    new_html = utils.add_embed(tweet_urls[-1]['href'])
    if new_html:
      el.insert_after(BeautifulSoup(new_html, 'html.parser'))
      el.decompose()

  for el in caas_body.find_all('a'):
    href = el.get('href')
    if href:
      el.attrs = {}
      el['href'] = href

  for el in caas_body.find_all(class_='caas-readmore'):
    el.decompose()

  content_html = caas_body.decode_contents()

  el = article_soup.find(attrs={"data-component":"ProsCons"})
  if el:
    new_html = ''
    for it in el.find_all('div', recursive=False):
      if it.find('ul'):
        new_html += '<h3>{}</h3><ul>'.format(it.h2.get_text())
        for li in it.find_all('li'):
          new_html += '<li>{}</li>'.format(li.get_text())
        new_html += '</ul>'
    content_html = new_html + content_html

  el = article_soup.find(attrs={"data-component":"ProductScores"})
  if el:
    for it in el.find_all('div'):
      score = it.get_text().strip()
      if score.isnumeric():
        content_html = '<h3>Review score: {}</h3>'.format(score) + content_html
        break

  el = caas_soup.find(class_=re.compile(r'caas-cover|caas-hero'))
  if el:
    if 'caas-figure' in el['class']:
      new_html = get_image(el)
      if new_html:
        content_html = new_html + content_html
    elif 'caas-carousel' in el['class']:
      # Slideshow - add lead image and remaining slides to end
      for i, slide in enumerate(el.find_all(class_='caas-carousel-slide')):
        content_html += '<h3>Gallery</h3>'
        new_html = get_image(slide)
        if new_html:
          if i == 0:
            content_html = new_html + content_html
          content_html += new_html
    elif 'yvideo' in el['class']:
      new_html = get_video(el)
      if new_html:
        content_html = new_html + content_html
    elif 'caas-iframe' in el['class']:
      new_html = get_iframe(el)
      if new_html:
        content_html = new_html + content_html
    else:
      logger.debug('unhandled caas-cover element type with classes {}'.format(str(el['class'])))

  item['content_html'] = content_html
  return item

def get_feed(args, save_debug=False):
  return rss.get_feed(args, save_debug, get_content)