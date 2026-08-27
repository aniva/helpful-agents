import cv2
print("OpenCV version:", cv2.__version__)

# Check for trackers in cv2
trackers = []
for name in dir(cv2):
    if "tracker" in name.lower():
        trackers.append("cv2." + name)

# Check for trackers in cv2.legacy
try:
    for name in dir(cv2.legacy):
        if "tracker" in name.lower():
            trackers.append("cv2.legacy." + name)
except AttributeError:
    pass

print("Available trackers:", trackers)
