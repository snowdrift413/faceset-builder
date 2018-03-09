import numpy as np
import sys
import os
import cv2
import face_recognition
from scipy.spatial import ConvexHull
from tqdm import tqdm
from . import imutils
from . import utils

class Photo_Collector:

    def __init__(self, target_faces, tolerance=0.5, min_face_size=256, crop_size=512, min_luminosity=10, max_luminosity=245, one_face=False, mask_faces=False):
        self.target_faces = target_faces
        self.tolerance = float(tolerance)
        self.min_face_size = int(round(min_face_size))
        self.crop_size = crop_size
        self.min_luminosity = min_luminosity
        self.max_luminosity = max_luminosity
        self.one_face = one_face
        self.mask_faces = mask_faces


    def cleanDuplicates(self, files, outdir, tolerance):
        hashes = dict()

        total = len(files)
        counter = 0

        for file in tqdm(files):
            counter += 1
            #progress = (counter/total)*100;
            #sys.stdout.write("\r{0:.3g}% \t".format(progress))
            
            img = cv2.imread(file)
            try:
                hs = imutils.dhash(img)
            except:
                #remove corrupted file
                os.remove(file)
                continue
            h, w = imutils.cv_size(img)
            size = int(round(h*w))

            smallest = False
            duplicate_name = ""
            for key, value in list(hashes.items()):
                if utils.get_num_bits_different(value[0], hs) <= tolerance:
                    if value[1] < size:
                        del hashes[key]
                        name = "duplicateof_{0}".format(os.path.basename(file))
                        os.remove(file)
                        #os.replace(key, os.path.join(outdir,name))
                        smallest = False
                    else:
                        smallest = True
                        duplicate_name = "duplicateof_{0}".format(os.path.basename(key))
                        
            if smallest:
                los = 1
                os.remove(file)
                #os.replace(file, os.path.join(outdir,duplicate_name))
            else:
                hashes[file] = [hs, size]
                
        return list(hashes.keys())
        
    
    def processPhotos(self, files, outdir, sample_height=500):
        total = len(files)
        counter = 0

        for file in tqdm(files):
            counter += 1
            #progress = (counter/total)*100;
            #sys.stdout.write("\r{0:.3g}% \t".format(progress))
            
            img = cv2.imread(file)
            rgb_img = img[:, :, ::-1]
            sample = imutils.downsampleToHeight(rgb_img, sample_height)

            s_height, s_width = imutils.cv_size(sample)
            o_height, o_width = imutils.cv_size(img)
            scale_factor = o_height/s_height

            face_locations = face_recognition.face_locations(sample, number_of_times_to_upsample=0, model="cnn")
            face_encodings = face_recognition.face_encodings(sample, face_locations)
            face_landmarks = face_recognition.face_landmarks(sample, face_locations)

            face_overlay = np.zeros((o_width, o_height), np.uint8)
            face_overlay.fill(255)
            tgt_face_poly = None

            crop_points = None
            
            for fenc, floc, flan in zip(face_encodings, face_locations, face_landmarks):
                result = face_recognition.compare_faces(self.target_faces, fenc, self.tolerance)

                #if the face found matches the target
                if any(result):
                    crop_points = imutils.scaleCoords(floc, imutils.cv_size(sample), imutils.cv_size(img))

                    if self.mask_faces:
                        tgt_face_poly = self.get_face_mask(flan, (1.2, 1.2, 1.2), scale_factor)
                    
                    #disqualified_dir = os.path.join(outdir,"2Dark_or_2Bright")
                    #os.makedirs(disqualified_dir, exist_ok=True)
                else:
                    if self.mask_faces:
                        face_polygon = self.get_face_mask(flan, (0.8, 0.95, 0.95), scale_factor)
                        cv2.fillConvexPoly(face_overlay, face_polygon.astype(int), 0)
            
            if crop_points != None:
                if self.mask_faces:
                    cv2.fillConvexPoly(face_overlay, tgt_face_poly.astype(int), 255)

                if self.mask_faces:
                    img = cv2.bitwise_and(img, img, mask=face_overlay)

                top, right, bottom, left = crop_points

                cropped = imutils.cropAsPaddedSquare(img, top, bottom, left, right)

                h, w = imutils.cv_size(cropped)
                if h > self.crop_size or w > self.crop_size:
                    try:
                        cropped = cv2.resize(cropped, (self.crop_size, self.crop_size))
                    except:
                      continue

                face = img[int(round(top)):int(round(bottom)), int(round(left)):int(round(right))]

                if self.validate_image(cropped, face):
                    outfile = os.path.join(outdir, "img_{0}.jpg".format(counter))
                    imutils.saveImage(cropped, outfile)



    def validate_image(self, cropped_img, face):
        face_h, face_w = imutils.cv_size(face)
        face_size = int(round(min(face_h, face_w)))
        luminance = int(round(imutils.getLuminosity(face)))
        #lapliance =
        #canny =

        if self.one_face and self.has_multiple_faces(cropped_img):
            return False

        if (face_size < self.min_face_size) or (not self.min_luminosity <= luminance <= self.max_luminosity) or imutils.isbw(cropped_img):
            return False

        return True



    @staticmethod
    def get_face_mask(landmarks, landmarks_scale, target_scale):

        chin_scale, nose_scale, brows_scale = landmarks_scale

        poly_chin = np.asarray(landmarks['chin'])
        poly_nose = np.asarray(landmarks['nose_tip']+landmarks['nose_bridge'])
        poly_brows = np.asarray(landmarks['left_eyebrow']+landmarks['right_eyebrow'])

        #get center of jawline polygon
        length = poly_chin.shape[0]
        sum_x = np.sum(poly_chin[:, 0])
        sum_y = np.sum(poly_chin[:, 1])
        center = sum_x / length, sum_y / length
        center = np.asarray([center])

        #scale down jawline polygon
        poly_chin = np.subtract(poly_chin, center)
        poly_chin *= chin_scale
        poly_chin = np.add(poly_chin, center)

        #get center of nose polygon
        length = poly_nose.shape[0]
        sum_x = np.sum(poly_nose[:, 0])
        sum_y = np.sum(poly_nose[:, 1])
        center = sum_x / length, sum_y / length
        center = np.asarray([center])

        #scale down nose polygon
        poly_nose = np.subtract(poly_nose, center)
        poly_nose *= nose_scale
        poly_nose = np.add(poly_nose, center)

        #get center of eyebrows polygon
        length = poly_brows.shape[0]
        sum_x = np.sum(poly_brows[:, 0])
        sum_y = np.sum(poly_brows[:, 1])
        center = sum_x / length, sum_y / length
        center = np.asarray([center])

        #scale down eyebrows polygon
        poly_brows = np.subtract(poly_brows, center)
        poly_brows *= brows_scale
        poly_brows = np.add(poly_brows, center)

        #combine polygons
        poly = np.concatenate([poly_chin, poly_brows, poly_nose])

        #get outline of polygon
        hull = ConvexHull(poly,)
        l = []
        for simplex in hull.vertices:
            l.append((poly[simplex, 0], poly[simplex,1]))

        poly = np.asarray(l)

        #scale coords
        poly *= target_scale
        return poly

    @staticmethod
    def has_multiple_faces(img):
        locations = face_recognition.face_locations(img, number_of_times_to_upsample=0, model="cnn")
        return (len(locations) > 1)


