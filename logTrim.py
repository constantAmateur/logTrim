#!/usr/bin/python
import os
import argparse
import re
import time
import sys

try:
  from humanize import naturalsize,naturaltime
except ImportError:
  def naturalsize(x,*args,**kw):
    return str(x)+"B"
  def naturaltime(x,*args,**kw):
    return str(x)+" seconds ago"

parser = argparse.ArgumentParser(description="Delete files matching a pattern to keep a certain maximum number and maintain a logarithmic spacing of copies in time.  One (and only one) of --max-no and --max-size must be given.")
parser.add_argument("pattern",type=str,help="The regular expression that matches files you want to process.")
parser.add_argument("dir",type=str,help="Directory to look for files",default=".")
parser.add_argument("--max-no",type=int,help="Number of files to keep.",default=None)
parser.add_argument("--max-size",type=str,help="Maximum disc usage, uses prefix B/K/M/G/T",default=None)
parser.add_argument("--max-age",type=str,help="Maximum age of file to keep.  Use prefix s/m/h/d/M/y",default=None)
parser.add_argument("--fake-equal-time-spacing",dest='equally_spaced',action='store_true',help="If this option is given, files are treated as if they are equally spaced in time.  This has the effect of preserving files closely spaced in time which would otherwise be discarded")
parser.add_argument("--allow-delete-all",action="store_true",help="If the requirements given result in all files being deleted, the script will usually stop with an error.  If this flag is specified it will instead proceed to delete everything.")
parser.add_argument("--dry-run",action="store_true",help="Runs everything, but doesn't actually delete anything.")
parser.add_argument("--verbose",action="store_true",help="Make the script chatty.")
parser.set_defaults(equally_spaced=False)
parser.set_defaults(verbose=False)
parser.set_defaults(allow_delete_all=False)
parser.set_defaults(dry_run=False)

args = parser.parse_args()
#Must use one of max_no or max_size
if (args.max_no is None and args.max_size is None) or (args.max_no and args.max_size):
  print "Must use only one of max_no or max_size."
  sys.exit(1)

#How to convert time units to seconds
time_prefix = {
    "s":1.0,
    "m":60.,
    "h":3600.,
    "d":86400.,
    "M":2592000.,
    "y":31536000,
    }
#How to convert size units to number of bytes
size_prefix = {
    "B":1.,
    "K":1024.,
    "M":1048576.,
    "G":1073741824.,
    "T":1099511627776.,
    }

if args.max_age:
  args.max_age = float(args.max_age[:-1])*time_prefix[args.max_age[-1]]
if args.max_size:
  args.max_size = float(args.max_size[:-1])*size_prefix[args.max_size[-1]]


os.chdir(args.dir)
#Get the list of files in target directory
files = os.listdir('.')
base = re.compile(args.pattern)
#Restrict to those that match the pattern given
files = [x for x in files if base.match(x)]
if len(files)==0:
  print "No files found. Exiting"
  sys.exit(1)
#Get their modification times
times = [os.path.getmtime(x) for x in files]
#Get current time
ctime = time.time()
#Shift all times relative to current time
times = [ctime-x for x in times]
#Get the file sizes
sizes = [os.path.getsize(x) for x in files]
#Zip them together and sort them
joined = zip(times,sizes,files)
joined.sort()
#If we're faking equal time spacing enter fake times here
if args.equally_spaced:
  joined = [(1.+i,joined[i][1],joined[i][2]) for i in xrange(len(times))]
#Keep a dictionary of those that need killing
to_kill={}
#Remove any that exceed the maximum age
if args.max_age:
  to_kill = {z:(x,y) for (x,y,z) in joined if x>args.max_age}
  joined = [(x,y,z) for (x,y,z) in joined if x<=args.max_age]
#Any individual files over the maximum size requirement need to be hosed too
if args.max_size:
  for (x,y,z) in joined:
    if y>args.max_size:
      to_kill[z]=(x,y)
  joined = [(x,y,z) for (x,y,z) in joined if y<=args.max_size]
times=[x for (x,y,z) in joined]
sizes=[y for (x,y,z) in joined]
files=[z for (x,y,z) in joined]
to_keep={}
if len(times)!=0:
  #Store the earliest time
  a=times[0]
  #And the latest
  b=times[-1]
  if args.max_age and b>args.max_age:
    b=args.max_age
  
  def keep_which_n(n):
    """
    Calculates which n files to keep
    to approximately log space the files
    in time.  Will prefer older times in case
    of a conflict.
    """
    #Return the whole lot if n is too large
    if n>=len(times):
      return {files[x]:sizes[x] for x in xrange(len(times))}
    keep={}
    efac=(b/a)**(1./(n-1)) if n!=1 else b/a
    target=a
    marker=0
    n_to_go=n
    n_left=len(times)
    while len(keep)<n:
      #Is the current one acceptable? If it's not acceptable
      #do we need to accept it anyway to make sure we get max_no
      #by the end?
      if times[marker]>=target or n_left==n_to_go:
        keep[files[marker]]=sizes[marker]
        marker=marker+1
        n_left=n_left-1
        n_to_go = n_to_go-1
        target=target*efac
      else:
        #Move onto the next one
        n_left=n_left-1
        marker=marker+1
    return keep
  
  #Require a certain number
  if args.max_no:
    if len(times)<args.max_no:
      print "Keeping %d files and found only %d.  Hence keeping them all."%(args.max_no,len(times))
      to_keep=dict(zip(files,sizes))
    else:
      to_keep=keep_which_n(args.max_no)
  elif args.max_size:
    if sum(sizes)<args.max_size:
      print "Max size is %s and files only take up %s.  Hence keeping them all."%(naturalsize(args.max_size),naturalsize(sum(sizes)))
      to_keep=dict(zip(files,sizes))
    else:
      #In this case we find the largest n we can keep that still satisfies our disc space requirement
      n=1
      tot_size=0
      while tot_size<args.max_size and n<len(times):
        last=to_keep
        to_keep=keep_which_n(n)
        tot_size=sum(to_keep.values())
        if args.verbose:
          print "For n=%d size is %s"%(n,naturalsize(tot_size))
        n=n+1
      to_keep=last

else:
  if not args.allow_delete_all:
    print "No valid set of files to keep found. Exiting"
    sys.exit(1)


if args.verbose:
  print "We are keeping %d files and killing %d of them."%(len(to_keep),len(to_kill)+len(files)-len(to_keep))
  for i in xrange(len(times)):
    status="kept" if files[i] in to_keep else "killed"
    print "%s last modified %s with size %s is being %s"%(files[i],naturaltime(times[i]),naturalsize(sizes[i]),status)
  #If we had some really bad ones, tell us about them too...
  if len(to_kill)!=0:
    for x in to_kill.keys():
      print "%s last modified %s with size %s is being killed because it is too large and/or old"%(x,naturaltime(to_kill[x][0]),naturalsize(to_kill[x][1]))

#Add in files which need killing
for i in xrange(len(files)):
  if files[i] not in to_keep:
    to_kill[files[i]]=(times[i],sizes[i])

#Kill those that need killing
if not args.dry_run:
  for doomed in to_kill.keys():
    os.remove(doomed)
