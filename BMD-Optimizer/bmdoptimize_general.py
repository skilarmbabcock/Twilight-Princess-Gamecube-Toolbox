import struct 
from io import BytesIO

def read_uint32(f):
    return struct.unpack(">I", f.read(4))[0]

def write_uint32(f, val):
    f.write(struct.pack(">I", val))


padstring = b"This is padding data to align"
def pad(f, value):
    nextAligned = (f.tell() + value-1) & ~(value - 1)
    for i in range(nextAligned - f.tell()):
        nextchar = i%len(padstring)
        f.write(padstring[nextchar:nextchar+1])
        

class Attribute(object):
    pass




def get_size(attr, compcount, datatype):
    if attr in (11, 12): # Color 
        if datatype in (0, 3): # RGB565/RGBA4
            return 2 
        elif datatype in (1, 2, 4, 5): # Various RGBA8 variants and RGBA6
            return 4 
    else:
        if datatype in (0, 1): # 1 Byte Signed/Unsigned
            datasize = 1
        elif datatype in (2, 3): # 2 Byte Signed/Unsigned
            datasize = 2 
        elif datatype in (4, ): # 4 Byte Signed/Unsigned
            datasize = 4 
        
        if attr == 9: # Position 
            if compcount == 0: # X Y
                return datasize*2
            elif compcount == 1: # X Y Z 
                return datasize*3
        if attr == 10: # Normal 
            if compcount == 0: # X Y Z 
                return datasize*3 
        if 13 <= attr <= 20: # Tex0-7
            if compcount == 0: # S 
                return datasize*1 
            if compcount == 1: # S T
                return datasize*2 
                
    raise RuntimeError("Unknown Attribute-Component Count-Data Type combo")
    

class VTX1(object):
    def __init__(self):
        self.data = b""
    
    @classmethod
    def from_file(cls, f):
        vtx = cls()
        start = f.tell()
        sectionname = f.read(4)
        vtx1size = read_uint32(f)
        #vtx.data = f.read(size-8)
        
        attribute_header_offset = read_uint32(f)
        vtx.attribute_header_offset = attribute_header_offset
        
        attribute_data_offsets = []
        for i in range(13):
            attribute_data_offsets.append(read_uint32(f))
            
        attribute_data_sizes = [] 
        
        for i in range(13):
            size = 0
            
            if attribute_data_offsets[i] != 0:
                for j in range(i+1, 13):
                    if j == 12:
                        size = vtx1size-attribute_data_offsets[i]
                        break 
                    else:
                        if attribute_data_offsets[j] == 0:
                            continue 
                        else:
                            size = attribute_data_offsets[j]-attribute_data_offsets[i]
                            break
                            
            attribute_data_sizes.append(size)
            
            
        attribute_data = []
        vtx.attribute_data  = attribute_data
        for i in range(13):
            f.seek(start+attribute_data_offsets[i])
            attribute_data.append(f.read(attribute_data_sizes[i]))
        f.seek(start+attribute_header_offset)
        attrib = read_uint32(f)
        i = 0
        
        attribute_info = {}
        vtx.attribute_info = attribute_info
        
        while attrib != 0xFF:
            #print(hex(f.tell()))
            #print(attrib)
            comp_count, comp_type, fraction, pad = struct.unpack(">IIB3s", f.read(12))
            
            attr = Attribute()
            attribute_info[attrib] = attr 
            attr.comp_count = comp_count
            attr.comp_type = comp_type
            attr.fraction = fraction 
            
            if attrib in (9, 10):
                attr.index = attrib-9
            elif 11 <= attrib <= 20:
                attr.index = attrib-8
            else:
                raise RuntimeError("Unknown attribute: "+ str(attrib))
            
            
            
            attrib = read_uint32(f) 
        
        f.seek(start+vtx1size)
        #for attr in attributedata:
        #    offset = attribute_data_offsets[attr.index]
        #    if attr in (11, 12): # Color
        #        if attr.comp_type
            
        
        return vtx 
        
    
    def write(self, f):
        start = f.tell()
        f.write(b"VTX1")
        f.write(b"F00F") # VTX1 size placeholder
        write_uint32(f, 0x40) # Offset to attribute header data 
        
        for i in range(13):
            write_uint32(f, 0)
        
        for attrkey in sorted(self.attribute_info.keys()):
            attr = self.attribute_info[attrkey]
            
            #print(attr)
            f.write(struct.pack(">IIIB3s", attrkey, attr.comp_count, attr.comp_type, attr.fraction, b"\xFF"*3))
        f.write(struct.pack(">IIIB3s", 0xFF, 1, 0, 0, b"\xFF"*3))
        
        for attrkey in sorted(self.attribute_info.keys()):
            attr = self.attribute_info[attrkey]
            attr.offset = f.tell()-start
            
            f.write(self.attribute_data[attr.index])
            pad(f, 32)
            
        vtxsize = f.tell()-start 
        f.seek(start+4)
        write_uint32(f, vtxsize)
        
        for attrkey in sorted(self.attribute_info.keys()):
            attr = self.attribute_info[attrkey]
            f.seek(start+12+4*attr.index)
            write_uint32(f, attr.offset)
            
        #write_uint32(f, len(self.data)+8)
        #f.write(self.data)
        f.seek(start+vtxsize)
        
        
class BMD(object):
    def __init__(self):
        self.header = b""
        self.sections = []
    
    @classmethod
    def from_file(cls, f):
        bmd = cls()
        bmd.header = f.read(32)
        
        size, sectioncount = struct.unpack_from(">II", bmd.header, 0x8)
        #print(bmd.header)
        #print(sectioncount)
        for i in range(sectioncount):
            sectionname = f.read(4)
            size = read_uint32(f)
            
            
            if sectionname == b"VTX1":
                f.seek(-8, 1)
                data = VTX1.from_file(f)
            else:
                data = f.read(size-8)
            
            bmd.sections.append((sectionname, data))
        
        return bmd 
    
    def get_section(self, name):
        for nm, data in self.sections:
            if nm == name:
                return data 
    
    def optimize(self, attr, comptype, fraction):
        vtx = self.get_section(b"VTX1")
        attrinfo = vtx.attribute_info[attr]
        attrdata = vtx.attribute_data[attrinfo.index]
        newdata = BytesIO()
        divergence = 0
        maxdiv = 0
        mindiv = 0
        maxedout = 0
        
        if attr == 9: # Position 
            if attrinfo.comp_type == 4 and comptype == 1: # Float to Signed8
                for i in range(len(attrdata)//(3*4)):
                    x, y, z = struct.unpack_from(">fff", attrdata, i*12)
                    
                    newx = round(max(min(x * (1 << fraction), 2**7-1), -(2**7)))
                    newy = round(max(min(y * (1 << fraction), 2**7-1), -(2**7)))
                    newz = round(max(min(z * (1 << fraction), 2**7-1), -(2**7)))
                    #print(x,y,z)
                    newdata.write(struct.pack(">bbb", newx, newy, newz))
                    
                    
                    if i < (len(attrdata)//(3*4)) - 3:
                        if abs(newx) >= 2**7: maxedout += 1
                        if abs(newy) >= 2**7: maxedout += 1
                        if abs(newz) >= 2**7: maxedout += 1
                        
                        backx = newx / (1<<fraction)
                        backy = newy / (1<<fraction)
                        backz = newz / (1<<fraction)
                        divergence+= abs(x-backx) 
                        divergence+= abs(y-backy) 
                        divergence+= abs(z-backz)
                        
            if attrinfo.comp_type == 4 and comptype == 3: # Float to Signed16
                for i in range(len(attrdata)//(3*4)):
                    x, y, z = struct.unpack_from(">fff", attrdata, i*12)
                    
                    newx = round(max(min(x * (1 << fraction), 2**15-1), -(2**15)))
                    newy = round(max(min(y * (1 << fraction), 2**15-1), -(2**15)))
                    newz = round(max(min(z * (1 << fraction), 2**15-1), -(2**15)))
                    #print(x,y,z)
                    newdata.write(struct.pack(">hhh", newx, newy, newz))
                    
                    
                    if i < (len(attrdata)//(3*4)) - 3:
                        if abs(newx) >= 2**15: maxedout += 1
                        if abs(newy) >= 2**15: maxedout += 1
                        if abs(newz) >= 2**15: maxedout += 1
                        
                        backx = newx / (1<<fraction)
                        backy = newy / (1<<fraction)
                        backz = newz / (1<<fraction)
                        divergence+= abs(x-backx) 
                        divergence+= abs(y-backy) 
                        divergence+= abs(z-backz)
                        
                        #if abs(x-backx)
                        
                        #print(x, backx)
        
        if attr == 10: # Normals 
            if attrinfo.comp_type == 3 and comptype == 1: # Float to Signed8
                for i in range(len(attrdata)//(3*2)):
                    x, y, z = struct.unpack_from(">hhh", attrdata, i*6)
                    #print(attrinfo.fraction)
                    #assert attrinfo.fraction == 15 
                    
                    x = x / (1 << attrinfo.fraction)
                    y = y / (1 << attrinfo.fraction)
                    z = z / (1 << attrinfo.fraction)
                    
                    newx = round(max(min(x * (1 << fraction), (2**7)-1), -2**7))
                    newy = round(max(min(y * (1 << fraction), (2**7)-1), -2**7))
                    newz = round(max(min(z * (1 << fraction), (2**7)-1), -2**7))
                    print(x, newx / (1<<fraction))
                    newdata.write(struct.pack(">bbb", newx, newy, newz))
        
        #print("total divergence:", divergence)
        #print("average divergence:", divergence/(len(attrdata)//(4)))
        attrinfo.comp_type = comptype 
        attrinfo.fraction = fraction 
        vtx.attribute_data[attrinfo.index] = newdata.getvalue()
        return maxedout, divergence, divergence/(len(attrdata)//(4))
    
    def write(self, f):
        f.write(self.header)
        for sectionname, data in self.sections:
            if sectionname == b"VTX1":
                data.write(f)
            else:
                f.write(sectionname)
                write_uint32(f, len(data)+8)
                f.write(data)
        
        size = f.tell()
        f.seek(8)
        write_uint32(f, size)
        write_uint32(f, len(self.sections))
                
        
if __name__ == "__main__":
    import os 
    import subprocess
    import sys 
    from distutils.dir_util import copy_tree
    
    optimizedir = sys.argv[1]
    print(optimizedir)
    resultdir = "optimizedmodels"
    totaldiv = 0 
    i = 0 
    totalmx = 0
    totaldivavg = 0
    for dirpath, dirnames, filenames in os.walk(optimizedir):# [("MRAM.arc_ext\\mram\\effect\\",[], ["bombhei_bomb.bmd"])]:#os.walk("MRAM.arc_ext"):
        for fname in filenames:
            if fname.endswith(".bmd"): 
                if fname == "bombhei_bomb.bmd":
                    continue 
                path = os.path.join(dirpath, fname)
                print(path)
                with open(path, "rb") as f:
                    bmd = BMD.from_file(f)
                    #mx, div, divavg = bmd.optimize(9, 3, 6) # Position
                    mx, div, divavg = bmd.optimize(9, 3, 6) 
                    #assert mx == 0
                    totalmx += mx 
                    totaldiv += div 
                    totaldivavg += divavg
                    if mx > 0:
                        print("maxed out")
                    i += 1
                    
                    #vtx = bmd.get_section(b"VTX1")
                    #if 10 in vtx.attribute_info:
                    #    bmd.optimize(10, 1, 7)
                with open(path, "wb") as f:
                    bmd.write(f)
                #outpath = path.replace(optimizedir, resultdir)
                #with open(outpath, "wb") as f:
                #    bmd.write(f)
    print("maxed out", totalmx)
    print("total div", totaldiv)
    print("avg div", totaldiv/i)
    print("avg div avg", totaldivavg/i)
    #subprocess.call(["python", r"C:\Users\User\Documents\GitHub\RARClib.py\rarc.py", "MRAM.arc_extOptimized", r"D:\Wii games\MKDDModdedFolder\P-GM4E\files\MRAM.arc"])
    
    
    #with open("bmdtest.bmd", "wb") as f:
    #    bmd.write(f)