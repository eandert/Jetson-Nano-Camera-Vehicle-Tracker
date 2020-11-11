# decompyle3 version 3.3.2
# Python bytecode 3.7 (3394)
# Decompiled from: Python 3.7.1 (v3.7.1:260ec2c36a, Oct 20 2018, 14:57:15) [MSC v.1915 64 bit (AMD64)]
# Embedded file name: C:\Yolo_v4\darknet\build\darknet\x64\car_video_rec.py
# Compiled at: 2020-08-28 19:43:12
# Size of source mod 2**32: 19704 bytes
from ctypes import *
import sys, math, random, os, cv2, numpy as np, time, csv, time, os
# Change folder so we can find where darknet is stored
sys.path.insert(1, 'C:/Yolo_v4/darknet/build/darknet/x64')
import darknet

from sklearn.neighbors import BallTree
KDTREESEARCH_LIMIT = 10000

class Tracked:

    def __init__(self, xmin, ymin, xmax, ymax, type, confidence, x, y, crossSection, time, id):
        self.xmin = xmin
        self.ymin = ymin
        self.xmax = xmax
        self.ymax = ymax
        self.x = x# * 0.3048
        self.y = y# * 0.3048
        self.lastX = self.x
        self.lastY = self.y
        self.dX = 0.0
        self.dY = 0.0
        self.timeToIntercept = 0.0
        #self.width = width
        #self.height = height
        self.typeArray = [0, 0, 0, 0]
        self.typeArray[type] += 1
        self.type = self.typeArray.index(max(self.typeArray))
        self.confidence = confidence
        self.lastTracked = time
        self.id = id
        self.relations = []
        self.velocity = 0
        self.lastVelocity = [0, 0, 0, 0, 0]
        self.lastTimePassed = 0
        self.lastXmin = 0
        self.lastYmin = 0
        self.lastXmax = 0
        self.lastYmax = 0
        self.lastX2min = 0
        self.lastY2min = 0
        self.lastX2max = 0
        self.lastY2max = 0
        self.lastHistory = 0
        self.crossSection = crossSection

        # Kalman filter for position
        self.acceleration = 0
        # Don't know this yet
        self.delta_t = 0
        # Transition matrix
        self.F_t = np.array([[1, 0, self.delta_t, 0], [0, 1, 0, self.delta_t], [0, 0, 1, 0], [0, 0, 0, 1]])
        # Initial State cov
        self.P_t = np.identity(4)
        # Process cov
        self.Q_t = np.identity(4)
        self.timeOfLifeInherited = 0
        # Initial State cov
        self.P_t = np.identity(4)
        # Process cov
        self.Q_t = np.identity(4)
        # Control matrix
        self.B_t = np.array([[0], [0], [0], [0]])
        # Control vector
        self.U_t = self.acceleration
        # Measurment Matrix
        self.H_t = np.array([[1, 0, 0, 0], [0, 1, 0, 0]])
        # Measurment cov
        self.R_t = np.identity(2)
        #Set up the first iteration params
        self.X_hat_t = np.array([[self.x], [self.y], [0], [0]])

    def update(self, position, other, time, timePassed):
        self.xmin = position[0]
        self.ymin = position[1]
        self.xmax = position[2]
        self.ymax = position[3]
        self.typeArray[other[0]] += 1
        self.type = self.typeArray.index(max(self.typeArray))
        self.confidence = other[1]
        # Covnert to meters from feet here
        x_measured = other[2]# * 0.3048
        y_measured = other[3]# * 0.3048
        self.crossSection = other[4]# * 0.3048

        # Kalman stuff
        # We have to change the transition matrix every time with the changed timestep
        self.F_t = np.array([[1, 0, timePassed, 0], [0, 1, 0, timePassed], [0, 0, 1, 0], [0, 0, 0, 1]])
        X_hat_t, self.P_hat_t = self.predictionKalman(self.X_hat_t, self.P_t, self.F_t, self.B_t, self.U_t, self.Q_t)
        measure_with_error = np.array([x_measured, y_measured])
        self.R_t = np.array([[1, 0],
                             [0, 1]])
        Z_t = (measure_with_error).transpose()
        Z_t = Z_t.reshape(Z_t.shape[0], -1)
        X_t, self.P_t = self.updateKalman(X_hat_t, self.P_hat_t, Z_t, self.R_t, self.H_t)
        self.X_hat_t = X_t
        self.P_hat_t = self.P_t
        # Now update our values for x and y
        self.x = .3*X_t[0][0] + .7*self.x
        self.y = .3*X_t[1][0] + .7*self.y

        # Velocity stuff
        # Calculate current velocity frame from the last 5 or less frames (if available)
        self.lastVelocity[self.lastHistory%5] = abs(math.hypot(self.x-self.lastX, self.y-self.lastY) / timePassed)
        self.lastHistory += 1
        if self.lastHistory >= 5:
            # We have 5 histories so divide by 5
            sum = 0
            for v in self.lastVelocity: sum += v
            self.velocity = sum/5.0
        else:
            # We have less than 5 histories, adjust as such
            sum = 0
            for v in self.lastVelocity: sum += v
            self.velocity = sum/self.lastHistory

        self.dX = (0.7*self.dX) + (0.3*(self.x - self.lastX))
        self.dY = (0.7*self.dY) + (0.3*(self.y - self.lastY))
        self.timeToIntercept = (0.3*(self.y / self.dY * (1 / 30.0))) + (0.7*self.timeToIntercept )
        self.lastX = self.x
        self.lastY = self.y
        self.lastTracked = time

    def predictionKalman(self, X_hat_t_1, P_t_1, F_t, B_t, U_t, Q_t):
        X_hat_t = F_t.dot(X_hat_t_1) + (B_t.dot(U_t).reshape(B_t.shape[0], -1))
        P_t = np.diag(np.diag(F_t.dot(P_t_1).dot(F_t.transpose()))) + Q_t
        return X_hat_t, P_t

    def updateKalman(self, X_hat_t, P_t, Z_t, R_t, H_t):

        K_prime = P_t.dot(H_t.transpose()).dot(np.linalg.inv(H_t.dot(P_t).dot(H_t.transpose()) + R_t))
        # print("K:\n",K_prime)
        # print("X_hat:\n",X_hat_t)
        X_t = X_hat_t + K_prime.dot(Z_t - H_t.dot(X_hat_t))
        P_t = P_t - K_prime.dot(H_t).dot(P_t)

        return X_t, P_t

    def getPosition(self):
        return [
         self.xmin, self.ymin, self.xmax, self.ymax]

    def getPositionPredicted(self):
        return [
         self.xminp, self.yminp, self.xmaxp, self.ymaxp]

    def calcEstimatedPos(self, timePassed):
        # A rolling average seems most effective for this as it can change rapidly
        if self.lastHistory >= 2:
            dxmin = (0.7 * (self.xmin - self.lastXmin) / (timePassed)) + (
                        0.3 * (self.lastXmin - self.lastX2min) / (self.lastTimePassed))
            dymin = (0.7 * (self.ymin - self.lastYmin) / (timePassed)) + (
                        0.3 * (self.lastYmin - self.lastY2min) / (self.lastTimePassed))
            dxmax = (0.7 * (self.xmax - self.lastXmax) / (timePassed)) + (
                        0.3 * (self.lastXmax - self.lastX2max) / (self.lastTimePassed))
            dymax = (0.7 * (self.ymax - self.lastYmax) / (timePassed)) + (
                        0.3 * (self.lastYmax - self.lastY2max) / (self.lastTimePassed))
            self.lastX2min = self.lastXmin
            self.lastY2min = self.lastYmin
            self.lastX2max = self.lastXmax
            self.lastY2max = self.lastYmax
            self.lastXmin = self.xmin
            self.lastYmin = self.ymin
            self.lastXmax = self.xmax
            self.lastYmax = self.ymax
            self.xminp = self.xmin + dxmin * timePassed
            self.yminp = self.ymin + dymin * timePassed
            self.xmaxp = self.xmax + dxmax * timePassed
            self.ymaxp = self.ymax + dymax * timePassed
            #print("xp, x ", self.xp, self.x)
            #print("yp, y ", self.yp, self.y)
            self.lastTimePassed = timePassed
            return
        if self.lastHistory == 1:
            dxmin = (self.xmin - self.lastXmin)/(timePassed)
            dymin = (self.ymin - self.lastYmin)/(timePassed)
            dxmax = (self.xmax - self.lastXmax) / (timePassed)
            dymax = (self.ymax - self.lastYmax) / (timePassed)
            self.lastX2min = self.lastXmin
            self.lastY2min = self.lastYmin
            self.lastX2max = self.lastXmax
            self.lastY2max = self.lastYmax
            self.lastXmin = self.xmin
            self.lastYmin = self.ymin
            self.lastXmax = self.xmax
            self.lastYmax = self.ymax
            self.xminp = self.xmin + dxmin * timePassed
            self.yminp = self.ymin + dymin * timePassed
            self.xmaxp = self.xmax + dxmax * timePassed
            self.ymaxp = self.ymax + dymax * timePassed
            #print("xp, x " , self.xp, self.x)
            #print("yp, y ", self.yp, self.y)
            self.lastTimePassed = timePassed
            return
        if self.lastHistory == 0:
            self.lastXmin = self.xmin
            self.lastYmin = self.ymin
            self.lastXmax = self.xmax
            self.lastYmax = self.ymax
            self.xminp = self.xmin
            self.yminp = self.ymin
            self.xmaxp = self.xmax
            self.ymaxp = self.ymax
            return


def convertBack(x, y, w, h):
    xmin = int(round(x - w / 2))
    xmax = int(round(x + w / 2))
    ymin = int(round(y - h / 2))
    ymax = int(round(y + h / 2))
    return (
     xmin, ymin, xmax, ymax)


# def computeDistance(bb0, bb1):
#     x0 = bb0[0] - bb0[2] / 2
#     x1 = bb0[0] + bb0[2] / 2
#     y0 = bb0[1] - bb0[3] / 2
#     y1 = bb0[1] + bb0[3] / 2
#     x10 = bb1[0] - bb1[2] / 2
#     x11 = bb1[0] + bb1[2] / 2
#     y10 = bb1[1] - bb1[3] / 2
#     y11 = bb1[1] + bb1[3] / 2
#     xA = max(x0, x10)
#     yA = max(y0, y10)
#     xB = min(x1, x11)
#     yB = min(y1, y11)
#     interArea = max(0, xB - xA + 1) * max(0, yB - yA + 1)
#     boxAArea = (x1 - x0 + 1) * (x1 - y0 + 1)
#     boxBArea = (x11 - x10 + 1) * (x11 - y10 + 1)
#     iou = interArea / float(boxAArea + boxBArea - interArea)
#     if iou <= 0:
#         distance = 1
#     else:
#         distance = 1 - iou
#     return distance

def computeDistance(a, b, epsilon=1e-5):

    """ Given two boxes `a` and `b` defined as a list of four numbers:
            [x1,y1,x2,y2]
        where:
            x1,y1 represent the upper left corner
            x2,y2 represent the lower right corner
        It returns the Intersect of Union score for these two boxes.

    Args:
        a:          (list of 4 numbers) [x1,y1,x2,y2]
        b:          (list of 4 numbers) [x1,y1,x2,y2]
        epsilon:    (float) Small value to prevent division by zero

    Returns:
        (float) The Intersect of Union score.
    """
    # COORDINATES OF THE INTERSECTION BOX
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])

    # AREA OF OVERLAP - Area where the boxes intersect
    width = (x2 - x1)
    height = (y2 - y1)
    # handle case where there is NO overlap
    if (width<0) or (height <0):
        return 1
    area_overlap = width * height

    # COMBINED AREA
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    area_combined = area_a + area_b - area_overlap

    # RATIO OF AREA OF OVERLAP OVER COMBINED AREA
    iou = area_overlap / (area_combined+epsilon)

    if iou <= 0:
        distance = 1
    else:
        distance = 1 - iou
    return distance


netMain = None
metaMain = None
altNames = None

firstIteration = True
yolo = None

class YOLO:

    def init(self, frame_width, frame_height, doImage, doWrite, timestamp):
        os.chdir('C:/Yolo_v4/darknet/build/darknet/x64/')
        #configPath = './cfg/yolov4-tiny.cfg'
        #weightPath = './weights/yolov4-tiny.weights'
        configPath = './cfg/yolov4-tiny.cfg'
        weightPath = './weights/yolov4-tiny.weights'
        metaPath = './cfg/coco.data'

        self.network, self.class_names, self.class_colors = darknet.load_network(
            configPath,
            metaPath,
            weightPath,
            batch_size=1
        )

        self.frame_height = frame_height
        self.frame_width = frame_width
        self.showImage = doImage
        self.write = doWrite
        if self.write:
            self.out = cv2.VideoWriter('output.avi', (cv2.VideoWriter_fourcc)(*'MJPG'), 10.0, (
             self.frame_width, self.frame_height))
        print('Starting the YOLO...')
        self.darknet_image = darknet.make_image(frame_width, frame_height, 3)
        self.trackedList = []
        self.id = 0
        self.time = 0
        self.prev_time = timestamp
        if self.showImage:
            cv2.startWindowThread()
            cv2.namedWindow('Demo')

    def cvDrawBoxes(self, detections, img, timestamp):
        color_dict = {'person':[
          0, 255, 255], 
         'bicycle':[238, 123, 158],  'car':[24, 245, 217],  'motorbike':[224, 119, 227],  'aeroplane':[
          154, 52, 104], 
         'bus':[179, 50, 247],  'train':[180, 164, 5],  'truck':[82, 42, 106],  'boat':[
          201, 25, 52], 
         'traffic light':[62, 17, 209],  'fire hydrant':[60, 68, 169],  'stop sign':[199, 113, 167],  'parking meter':[
          19, 71, 68], 
         'bench':[161, 83, 182],  'bird':[75, 6, 145],  'cat':[100, 64, 151],  'dog':[
          156, 116, 171], 
         'horse':[88, 9, 123],  'sheep':[181, 86, 222],  'cow':[116, 238, 87],  'elephant':[74, 90, 143],  'bear':[
          249, 157, 47], 
         'zebra':[26, 101, 131],  'giraffe':[195, 130, 181],  'backpack':[242, 52, 233],  'umbrella':[
          131, 11, 189], 
         'handbag':[221, 229, 176],  'tie':[193, 56, 44],  'suitcase':[139, 53, 137],  'frisbee':[
          102, 208, 40], 
         'skis':[61, 50, 7],  'snowboard':[65, 82, 186],  'sports ball':[65, 82, 186],  'kite':[
          153, 254, 81], 
         'baseball bat':[233, 80, 195],  'baseball glove':[165, 179, 213],  'skateboard':[57, 65, 211],  'surfboard':[
          98, 255, 164], 
         'tennis racket':[205, 219, 146],  'bottle':[140, 138, 172],  'wine glass':[23, 53, 119],  'cup':[
          102, 215, 88], 
         'fork':[198, 204, 245],  'knife':[183, 132, 233],  'spoon':[14, 87, 125],  'bowl':[
          221, 43, 104], 
         'banana':[181, 215, 6],  'apple':[16, 139, 183],  'sandwich':[150, 136, 166],  'orange':[219, 144, 1],  'broccoli':[
          123, 226, 195], 
         'carrot':[230, 45, 209],  'hot dog':[252, 215, 56],  'pizza':[234, 170, 131],  'donut':[
          36, 208, 234], 
         'cake':[19, 24, 2],  'chair':[115, 184, 234],  'sofa':[125, 238, 12],  'pottedplant':[
          57, 226, 76], 
         'bed':[77, 31, 134],  'diningtable':[208, 202, 204],  'toilet':[208, 202, 204],  'tvmonitor':[
          208, 202, 204], 
         'laptop':[159, 149, 163],  'mouse':[148, 148, 87],  'remote':[171, 107, 183],  'keyboard':[
          33, 154, 135], 
         'cell phone':[206, 209, 108],  'microwave':[206, 209, 108],  'oven':[97, 246, 15],  'toaster':[
          147, 140, 184], 
         'sink':[157, 58, 24],  'refrigerator':[117, 145, 137],  'book':[155, 129, 244],  'clock':[
          53, 61, 6], 
         'vase':[145, 75, 152],  'scissors':[8, 140, 38],  'teddy bear':[37, 61, 220],  'hair drier':[
          129, 12, 229], 
         'toothbrush':[11, 126, 158]}
        cars = 0
        trucks = 0
        buses = 0
        total = 0
        tracked_items = [
         'car', 'truck', 'bus', 'motorbike']
        localization_items = [
            'traffic light',  'fire hydrant',  'stop sign',  'parking meter']
        detections_list = []
        detections_position_list = []
        for label, confidence, bbox in detections:
            x, y, w, h = (bbox[0],
             bbox[1],
             bbox[2],
             bbox[3])
            name_tag = label
            for name_key, color_val in color_dict.items():
                if name_key == name_tag:
                    cameraAdjustementAngle = 15.0
                    hFOV = 157.0  # 2 * math.atan( / focalLength)
                    vFOV = 155.0
                    imageWidth = 1920
                    imageHeight = 1080
                    #focalLength = 98.9 * (hFOV/2.9)
                    focalLength = imageHeight / 2 / math.tan(vFOV / 2.0)
                    #focalLength = 5
                    # = (2 * 3.14 * focalLength) / (w + h * 360) * 1000 + 3
                    # 1/d_o + 1/d_i = 1/f.
                    #ObjectHeight = 1.5
                    # ObjectHeight =
                    if name_tag == 'car':
                        cars += 1
                        total += 1
                        ObjectHeight = 1.5
                    elif name_tag == 'truck':
                        trucks += 1
                        total += 1
                        ObjectHeight = 3.0
                    elif name_tag == 'bus':
                        buses += 1
                        total += 1
                        ObjectHeight = 3.0
                    else:
                        ObjectHeight = 1.8
                    SensorHeight = 1.25 #21.21
                    ObjectHeightOnSensor = SensorHeight * h / imageHeight
                    distancei = (focalLength * ObjectHeight)/ObjectHeightOnSensor
                    if name_key in tracked_items:
                        # Old way
                        #detections_position_list.append([x, y, w, h])
                        # New Way
                        #sin(x_dist/dist)
                        # Calculate x and y position based on camera FOV
                        angle = math.radians(((x-(imageWidth/2.0)) * (hFOV/imageWidth)) + cameraAdjustementAngle)
                        x_actual = math.sin(angle) * distancei / 1000.0
                        y_actual = distancei / 1000.0
                        xmin, ymin, xmax, ymax = convertBack(float(x), float(y),
                                                             float(w), float(h))
                        detections_position_list.append([xmin, ymin, xmax, ymax])
                        # Calculate the crosssection (width) of vehicle being detected for error math
                        crossSection = math.sin(math.radians((xmax - xmin) * (SensorHeight / 1920))) * distancei
                        detections_list.append([tracked_items.index(name_key), confidence * 100, x_actual, y_actual, crossSection])
                        # pt1 = (xmin, ymin)
                        # pt2 = (xmax, ymax)
                        # cv2.rectangle(img, pt1, pt2, [8, 140, 38], 1)
                        # cv2.putText(img, "NA" + ' t:' + str(name_tag) + ' d:' + str(
                        #     distancei), (
                        #                 pt1[0], pt1[1] - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, [8, 140, 38], 2)
                    # if name_key in localization_items:
                    #     xmin, ymin, xmax, ymax = convertBack(float(x), float(y),
                    #                                          float(w), float(h))
                    #     pt1 = (xmin, ymin)
                    #     pt2 = (xmax, ymax)
                    #     cv2.rectangle(img, pt1, pt2, [8, 140, 38], 1)
                    #     cv2.putText(img, "L" + ' t:' + str(name_tag) + ' d:' + str(
                    #         distancei), (
                    #                     pt1[0], pt1[1] - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, [8, 140, 38], 2)

        # for track in self.trackedList:
        #     track.calcEstimatedPos(timestamp - self.prev_time)
        #     pt1 = (track.xmin, track.ymin)
        #     pt2 = (track.xmax, track.ymax)
        #     color = color_dict[tracked_items[track.type]]
        #     cv2.rectangle(img, pt1, pt2, color, 1)
        #     cv2.putText(img, str(track.id) + ' t:' + str(tracked_items[track.type]) + ' d:' + str(
        #         track.distance) + ' v:' + str(track.velocity), (
        #                     pt1[0], pt1[1] - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        self.matchDetections(detections_position_list, detections_list, timestamp)

        for detection in self.trackedList:
            if detection.lastHistory >= 1:
                #xmin, ymin, xmax, ymax = convertBack(float(detection.x), float(detection.y), float(detection.width), float(detection.height))
                pt1 = (detection.xmin, detection.ymin)
                pt2 = (detection.xmax, detection.ymax)
                color = color_dict[tracked_items[detection.type]]
                if -0.5 <= detection.x <= 0.5 and 0.0 <= detection.timeToIntercept <= 2.5:
                    cv2.rectangle(img, pt1, pt2, [255, 0, 0], -1)
                    cv2.putText(img, str(
                        round(detection.timeToIntercept, 2)), (
                                    pt1[0], pt1[1] + 25), cv2.FONT_HERSHEY_SIMPLEX, 1.5, [255, 255, 255], 2)
                else:
                    cv2.rectangle(img, pt1, pt2, color, 1)
                cv2.putText(img, str(detection.id) + ' t:' + str(tracked_items[detection.type]) + ' x:' + str(
                    round(detection.x, 2)) + ' y:' + str(round(detection.y, 2)), (
                                pt1[0], pt1[1] - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        print('Time:', timestamp, ' Total:', total, ' Cars:', cars, ' Trucks:', trucks, ' Buses:', buses)
        return img

    def readFrame(self, frame_read, timestamp):
        #try:
        ptime = time.time()
        #darknet_image = self.darknet.make_image(self.frame_width, self.frame_height, 3)
        frame_rgb = cv2.cvtColor(frame_read, cv2.COLOR_BGR2RGB)
        frame_resized = cv2.resize(frame_rgb, (
         self.frame_width, self.frame_height),
          interpolation=(cv2.INTER_LINEAR))
        darknet.copy_image_from_bytes(self.darknet_image, frame_resized.tobytes())
        detections = darknet.detect_image(self.network, self.class_names, self.darknet_image, thresh=0.25)
        #darknet.free_image(darknet_image)
        image = self.cvDrawBoxes(detections, frame_resized, timestamp)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        print(" Current YOLO Processing Framerate: ", 1 / (time.time() - ptime))
        if self.showImage:
            cv2.imshow('Demo', image)
            if cv2.waitKey(1) == 27:
                exit(0)
        if self.write:
            self.out.write(image)
        print(" Print to screen framerate: ", 1 / (time.time() - ptime))
        self.prev_time = timestamp
        #except Exception as e:
        #    print(e)
        #    return timestamp, []

    def matchDetections(self, detections_list_positions, detection_list, timestamp):
        self.time += 1
        matches = []
        if len(detections_list_positions) > 0:
            if len(self.trackedList) > 0:
                numpy_formatted = np.array(detections_list_positions).reshape(len(detections_list_positions), 4)
                thisFrameTrackTree = BallTree(numpy_formatted, metric=computeDistance)

                # Need to check the tree size here in order to figure out if we can even do this
                length = len(numpy_formatted)
                if length > 0:
                    for trackedListIdx, track in enumerate(self.trackedList):
                        track.calcEstimatedPos(timestamp - self.prev_time)
                        tuple = thisFrameTrackTree.query((np.array([track.getPositionPredicted()])), k=length, return_distance=True)
                        #print(track.id, len(tuple) , tuple)
                        #if len(tuple[0]) != 0:
                        first = True
                        for IOUVsDetection, detectionIdx in zip(tuple[0][0], tuple[1][0]):
                            #print(tup1[0], tup2[0])
                            if .95 >= IOUVsDetection >= 0:
                                # Only grab the first match
                                # Before determining if this is a match check if this detection has been matched already
                                if first:
                                    try:
                                        index = [i[0] for i in matches].index(detectionIdx)
                                        # We have found the detection index, lets see which track is a better match
                                        if matches[index][2] > IOUVsDetection:
                                            # We are better so add ourselves
                                            matches.append([detectionIdx, trackedListIdx, IOUVsDetection])
                                            # Now unmatch the other one because we are better
                                            # This essentiall eliminates double matching
                                            matches[index][2] = 1
                                            matches[index][1] = -99
                                            # Now break the loop
                                            first = False
                                    except:
                                        # No matches in the list, go ahead and add
                                        matches.append([detectionIdx, trackedListIdx, IOUVsDetection])
                                        first = False

                                    # Old way, eliminating
                                    #track.relations.append([tup1[0], tup2[0]])
                                    #first = True
                                else:
                                    # The other matches need to be marked so they arent made into a new track
                                    # Set distance to 1 so we know this wasn't the main match
                                    if detectionIdx not in [i[0] for i in matches]:
                                        # No matches in the list, go ahead and add
                                        matches.append([detectionIdx, -99, 1])

                        # Old method
                        # if tuple[0][0][0] < 1:
                        #     track.relations.append([tuple[0][0][0], tuple[1][0][0]])
                        #     matches.append(tuple[1][0][0])

                # update the tracks that made it through
                for match in matches:
                    if match[1] != -99:
                        # Now append to the correct track
                        self.trackedList[match[1]].relations.append([match[0], match[2]])
                        #self.trackedList[match[1]].update(detections_list_positions[match[0]],
                        #             detection_list[match[0]], self.time, timestamp - self.prev_time)

                # Old way
                for track in self.trackedList:
                    if len(track.relations) == 1:
                        # Single mathc, go ahead and update the location
                        track.update(detections_list_positions[track.relations[0][0]], detection_list[track.relations[0][0]], self.time, timestamp - self.prev_time)
                    elif len(track.relations) > 1:
                        # if we have multiple matches, pick the best one
                        #print(' 2 matches for! ', track.id)
                        max = 0
                        idx = -99
                        for rel in track.relations:
                            #print ( " Comparing ", rel[0], rel[1])
                            if rel[1] < max:
                                max = rel[1]
                                idx = rel[0]

                        if idx != -99:
                            track.update(detections_list_positions[idx], detection_list[idx])

                if len(matches):
                    missing = sorted(set(range(0, len(detections_list_positions))) - set([i[0] for i in matches]))
                else:
                    missing = list(range(0, len(detections_list_positions)))

                added = []
                for add in missing:
                    # Before we add anything, let's check back against the list to make sure there is no IOU match over .75 with this new item and another new item
                    tuple = thisFrameTrackTree.query((np.array([detections_list_positions[add]])), k=length,
                                                     return_distance=True)
                    first = True
                    #print("Comparision IOU: ", add, tuple)
                    #print("       List  : ", tuple[0], tuple[1])
                    for IOUVsDetection, detectionIdx in zip(tuple[0][0], tuple[1][0]):
                        # print(tup1[0], tup2[0])
                        #if add == tup2[0]:
                        #print("Comparision IOU: ", tup1, tup2)
                        # Check to make sure thie IOU match is high
                        if .75 >= IOUVsDetection >= 0:
                            # Make sure this is not ourself
                            if add != detectionIdx:
                                # If this is not ourself, add ourself only if none of our matches has been added yet
                                if detectionIdx in added:
                                    #print("Match found in added: ", add, detectionIdx)
                                    first = False
                                    break
                            #else:
                                #print ( "Ourself: ", add, detectionIdx )

                    # We are the best according to arbitrarily broken tie and can be added
                    if first:
                        print ( "Adding: ", add )
                        added.append(add)
                        new = Tracked(detections_list_positions[add][0], detections_list_positions[add][1], detections_list_positions[add][2], detections_list_positions[add][3], detection_list[add][0], detection_list[add][1], detection_list[add][2], detection_list[add][3], detection_list[add][4], self.time, self.id)
                        if self.id < 1000000:
                            self.id += 1
                        else:
                            self.id = 0
                        self.trackedList.append(new)

            else:
                for dl, dlp in zip(detection_list, detections_list_positions):
                    new = Tracked(dlp[0], dlp[1], dlp[2], dlp[3], dl[0], dl[1], dl[2], dl[3], dl[4], self.time, self.id)
                    if self.id < 1000:
                        self.id += 1
                    else:
                        self.id = 0
                    self.trackedList.append(new)

        remove = []
        for idx, track in enumerate(self.trackedList):
            track.relations = []
            if track.lastTracked < self.time - 5:
                remove.append(idx)
                print ( " Removing ", idx)

        for delete in reversed(remove):
            self.trackedList.pop(delete)

    def endVideo(self):
        self.out.release()


def processImages(q):
    global firstIteration
    global yolo

    print ( "Producer: Process image called! ")

    # Check for images, timestamps in the queue
    while 1:
        if not q.empty():
            # Get the image from the queue
            jpg = q.get()

            # Do the opencv image parsing
            i = jpg[0]

            # We do some special setup if this is the first frame, otherwise just send the image
            if firstIteration:
                # Setup the variables we need, hopefully this function stays active
                yolo = YOLO()
                height, width = i.shape[:2]
                #print(width, height)
                yolo.init(width, height, True, False, jpg[1])
                firstIteration = False
            #print("Producer: Got an image at ", jpg[1])
            yolo.readFrame(i, jpg[1])
            #print ( "Sending tracks ", result)