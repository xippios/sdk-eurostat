- The nightly live run compares each of the eighteen packaged codelists with the list
  Eurostat serves now, one request each, and leaves the table of contents out, since each of
  its leaves carries its dataset's last update. With its seven other tests the run asks for
  25 answers where 0.3.0's asked for 18, and the client's cache answers the second request
  for STATINFO when it comes within five minutes of the first. The refresh scripts run on
  core's frames, the snapshot through a client of Eurostat's website that waits as long as a
  429 asks.
  (https://github.com/xippios/sdk-eurostat/issues/54, https://github.com/xippios/sdk-eurostat/issues/55, https://github.com/xippios/sdk-eurostat/issues/56)
