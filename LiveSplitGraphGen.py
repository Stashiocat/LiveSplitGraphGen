from lxml import etree
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.ticker as tkr
import math
from datetime import datetime
import pandas as pd
import sys
import re

def GetRunDuration(startTime, endTime):
    startTime = datetime.strptime(startTime, "%m/%d/%Y %H:%M:%S")
    endTime = datetime.strptime(endTime, "%m/%d/%Y %H:%M:%S")
    return ((endTime - startTime).total_seconds() / 60.0)
    
def TimeToSeconds(inTime):
    [hours, minutes, seconds] = [float(x) for x in inTime.split(':')]
    return hours*3600.0 + minutes*60.0 + seconds
    
def GetAttemptedHistory(Tree):
    outTimes = []
    outDates = []
    outRunDurations = []
    outRunComplete = []
    for AttemptSeg in Tree.find("AttemptHistory"):
        id = AttemptSeg.attrib["id"]
        if int(id) > 0:
            if "started" in AttemptSeg.attrib and "ended" in AttemptSeg.attrib:
                startDate = AttemptSeg.attrib["started"]
                endDate = AttemptSeg.attrib["ended"]
                runDur = GetRunDuration(startDate, endDate)
                runComplete = False
                outRunDurations.append(runDur)
                for Attempt in AttemptSeg:
                    if Attempt is not None:
                        if Attempt.tag == "RealTime":
                            realTime = TimeToSeconds(Attempt.text)
                            outTimes.append(realTime)
                            outDates.append(startDate)
                            runComplete = True
                outRunComplete.append(runComplete)
    return outTimes, outDates, outRunDurations, outRunComplete

def GetFilenameNoExt(InFilename):
    return InFilename.split('.')[0]
    
def SetUpDirectory(Directory):
    Path(Directory).mkdir(exist_ok=True)

def GetSegmentName(inSegment):
    return inSegment.find("Name").text

def GetSafeName(inName):
    return re.sub(r'[\\/*?:"<>|]',"", inName)
    
# Returns a list of RealTimes for a given segment (in seconds)
def GetSegmentHistory(inSegment):
    segHist = inSegment.find("SegmentHistory")
    
    if segHist is None:
        return None
        
    outTimes = []
    
    for time in segHist:
        realTimeSeg = time.find("RealTime")
        if realTimeSeg is not None:
            realTime = TimeToSeconds(realTimeSeg.text)
            outTimes.append(realTime)
        
    return outTimes

# BuildRealTimeMapping() Output looks like this:
# {
#     "Bombs":
#     {
#         "ids": {
#             "1": <RealTime value in seconds>,
#             "2": <RealTime value in seconds>,
#             "4": <RealTime value in seconds>,
#             "7": <RealTime value in seconds>,
#             "8": <RealTime value in seconds>
#         },
#         "name": "Bombs"
#     },
#     "Charge":
#     {
#         "ids": {
#             "1": <RealTime value in seconds>,
#             "2": <RealTime value in seconds>
#             "7": <RealTime value in seconds>,
#         },
#         "name": "Charge"
#     },
#     ...
# }
def BuildRealTimeMapping(Tree):
    outTable = dict()
    i = 0
    for Seg in Tree.find("Segments"):
        segName = GetSegmentName(Seg)
        segHist = Seg.find("SegmentHistory")
        
        if segName in outTable:
            i += 1
            segName += str(i)
        
        if not segName in outTable:
            outTable[segName] = dict()
            outTable[segName]['ids'] = dict()
        
        for time in segHist:
            id = time.attrib["id"]
            if int(id) > 0:
                realTimeSeg = time.find("RealTime")
                if realTimeSeg is not None:
                    realTime = TimeToSeconds(realTimeSeg.text)
                    outTable[segName]['ids'][id] = realTime
                    outTable[segName]['name'] = segName
                
                
    return outTable

def TimeFormatter(time, pos):
    h = int(time / 3600)
    m = int((time % 3600) / 60)
    s = int((time % 3600) % 60)
    if h > 0:
        return "%dh %dm %ds" % (h, m, s)
    elif m > 0:
        return "%dm %ds" % (m, s)
    return "%ds" % (s)

def DumpSegmentGraphToFile(Directory, Seg):
    SegHist = GetSegmentHistory(Seg)
    if SegHist is not None:
        fig = plt.figure()
        ax = fig.add_subplot(1, 1, 1)
        ax.set_title("Segment Length: %s" % (GetSegmentName(Seg)))
        ax.set_xlabel("Run")
        ax.set_ylabel("Time")
        ax.yaxis.set_major_formatter(tkr.FuncFormatter(TimeFormatter))
        
        # Was messing with using Pandas to remove outliers, since those aren't helpful
        p = pd.Series(SegHist)
        p = p[p.between(p.quantile(0.00), p.quantile(0.95))]
        
        ax.scatter([i+1 for i in range(len(p))], p, s=3)
        plt.xticks(rotation=90)
        plt.savefig("%s/SegmentLength_%s.png" % (Directory, GetSafeName(Seg.find("Name").text)), bbox_inches='tight')
        plt.close(fig)

def DumpSegments(Directory, Tree):
    for Seg in Tree.find("Segments"):
        DumpSegmentGraphToFile(Directory, Seg)

def DumpBestTimesToSegment(Directory, Tree, RealTimeMapping):
    RealTimeMapping = BuildRealTimeMapping(Tree)
    SegTimesById = dict()
    
    for Seg in RealTimeMapping:
        segTimes = []
        for id in RealTimeMapping[Seg]['ids']:
            if not id in SegTimesById:
                SegTimesById[id] = 0.0
            SegTimesById[id] += RealTimeMapping[Seg]['ids'][id]
            segTimes.append(SegTimesById[id])
        fig = plt.figure()
        ax = fig.add_subplot(1, 1, 1)
        ax.set_title("Run time at segment: %s" % (RealTimeMapping[Seg]['name']))
        ax.set_xlabel("Run")
        ax.set_ylabel("Time")
        ax.yaxis.set_major_formatter(tkr.FuncFormatter(TimeFormatter))
        p = pd.Series(segTimes)
        p = p[p.between(p.quantile(0.00), p.quantile(0.95))]
        #ax.plot(p)
        
        ax.scatter([i+1 for i in range(len(p))], p, s=3)
        plt.xticks(rotation=90)
        safe_name = GetSafeName(RealTimeMapping[Seg]['name'])
        plt.savefig("%s/TimeAtSegment_%s.png" % (Directory, safe_name), bbox_inches='tight')
        plt.close(fig)
        
    
def DumpCompletedRuns(Directory, AttemptHistory, AttemptDates):
    
    fig, ax = plt.subplots()
    fig.set_size_inches(30.5, 10.5)
    ax.set_title("Completed Runs (%d)" % len(AttemptHistory))
    ax.set_xlabel("Run")
    ax.set_ylabel("Time")
    ax.yaxis.set_major_formatter(tkr.FuncFormatter(TimeFormatter))
    low = min(AttemptHistory)
    high = max(AttemptHistory)
    plt.ylim([math.ceil(low-0.1*(high-low)), math.ceil(high+0.1*(high-low))])
    plt.grid(True)
    
    colors = []
    m = high+1
    for t in AttemptHistory:
        if t < m:
            m = t
            colors.append('r')
        else:
            colors.append('b')
            
    ax.bar(AttemptDates, AttemptHistory, color=colors)
    plt.xticks(rotation=90)
    plt.savefig("%s/CompletedRuns.png" % (Directory), bbox_inches='tight')
    plt.close(fig)
            
def DumpRunDurations(Directory, RunDurations, RunComplete):
    runsLength = len(RunDurations)
    runs = [i+1 for i in range(runsLength)]
    colors = [('green' if r else 'red') for r in RunComplete]
    fig, ax = plt.subplots()
    ax.set_title("Run Durations")
    ax.set_xlabel("Run")
    ax.set_ylabel("Time (minutes)")
    ax.scatter(runs, RunDurations, s=3, c=colors)
    plt.grid(True)
    plt.savefig("%s/RunDurations.png" % (Directory), bbox_inches='tight')

if __name__ == '__main__':

    ###########################
    # Setup
    ###########################
    
    # Default filename
    SplitFilename = r"Super Metroid Any%.lss"

    # Check program arguments for a given filename
    if len(sys.argv) > 1:
        SplitFilename = ' '.join(sys.argv[1:])
        
    # Get the name of the file without the file extension
    Directory = GetFilenameNoExt(SplitFilename)

    # Make sure the output directory exists
    SetUpDirectory(Directory)

    # parse the XML file
    Tree = etree.parse(SplitFilename)
    
    # Parse out attempt and run information
    # AttemptHistory = list of *completed* run times (realtime, in seconds)
    # AttemptDates   = list of date/times that each *completed* run was started
    # RunDurations   = list of run lengths (this includes both complete and incomplete runs)
    # RunComplete    = list containing whether the run finished or not
    AttemptHistory, AttemptDates, RunDurations, RunComplete = GetAttemptedHistory(Tree)

    # Build a mapping from segment -> real time for each run (in seconds)
    RealTimeMapping = BuildRealTimeMapping(Tree)

    ###########################
    # Output graphs
    ###########################
    
    # Output graphs for segment times (this is the time that just this segment took, starting from the previous segment)
    print("Outputting segments... ")
    DumpSegments(Directory, Tree)
    
    # Output graphs for best times being at a segment (this is the time since the start of the run)
    print("Outputting best times to segments... ")
    DumpBestTimesToSegment(Directory, Tree, RealTimeMapping)
    
    # Output a graph for each completed run
    print("Outputting completed runs... ")
    DumpCompletedRuns(Directory, AttemptHistory, AttemptDates)
    
    # Output a graph with all run durations, showing completed and non-completed runs
    print("Outputting run durations... ")
    DumpRunDurations(Directory, RunDurations, RunComplete)
