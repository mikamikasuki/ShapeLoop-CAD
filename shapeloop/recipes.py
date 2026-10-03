"""Original editable starting recipes, evaluated at build time."""
from .spec import DesignSpec

def _parameter(value, dimension="length", description=""):
    return {"value":value,"dimension":dimension,"description":description}

def _feature(id, type, part, parameters, inputs=(), roles=()):
    return {"id":id,"name":id.replace('_',' ').title(),"type":type,"part":part,"parameters":parameters,"inputs":list(inputs),"roles":list(roles)}

def _constraint(id,type,parameters,features=(),tolerance=.01):
    return {"id":id,"name":id.replace('_',' ').title(),"type":type,"parameters":parameters,"features":list(features),"tolerance":tolerance,"required":True}

def recipe(name: str) -> DesignSpec:
    if name == "enclosure":
        params={"width":_parameter(80),"depth":_parameter(50),"height":_parameter(30),"wall":_parameter(2),"lid_thickness":_parameter(2),"hole_diameter":_parameter(3),"mount_x":_parameter(30),"mount_y":_parameter(15),"boss_diameter":_parameter(8),"fillet_radius":_parameter(.8)}
        centers=[["-mount_x","-mount_y",0],["mount_x","-mount_y",0],["mount_x","mount_y",0],["-mount_x","mount_y",0]]
        features=[
            _feature("body_blank","box","body",{"size":["width","depth","height-lid_thickness"],"center":[0,0,"(height-lid_thickness)/2"]}),
            _feature("body_cavity","pocket","body",{"size":["width-2*wall","depth-2*wall","height"],"center":[0,0,"wall+height/2"]},["body_blank"],["interior"]),
            _feature("bosses","pattern","body",{"profile":"cylinder","centers":centers,"diameter":"boss_diameter","height":"height-lid_thickness","z":0},["body_cavity"],["mounting_bosses"]),
            _feature("mount_holes","hole","body",{"centers":centers,"diameter":"hole_diameter","depth":"height+2*wall","start":-1,"axis":"Z"},["bosses"],["mounting_pattern"]),
            _feature("body_edges","fillet","body",{"radius":"fillet_radius","selector":"outer_vertical"},["mount_holes"]),
            _feature("lid_blank","box","lid",{"size":["width","depth","lid_thickness"],"center":[0,0,"height-lid_thickness/2"]}),
            _feature("lid_holes","hole","lid",{"centers":centers,"diameter":"hole_diameter","depth":"height+2*wall","start":-1,"axis":"Z"},["lid_blank"],["mounting_pattern"]),
        ]
        constraints=[_constraint("envelope","envelope",{"size":["width","depth","height"],"center":[0,0,"height/2"],"frame":"origin"}),
            _constraint("mounting_pattern","hole_pattern",{"part":"body","diameter":"hole_diameter","centers":centers,"axis":"Z","count":4},["mount_holes"]),
            _constraint("lid_pattern","hole_pattern",{"part":"lid","diameter":"hole_diameter","centers":centers,"axis":"Z","count":4},["lid_holes"]),
            _constraint("base_thickness","thickness",{"part":"body","start":[0,0,-1],"direction":[0,0,1],"length":"height+2*wall","expected":"wall"},["body_cavity"]),
            _constraint("body_lid_contact","interference",{"parts":["body","lid"],"allowed_contact":True,"volume_tolerance":.001}),
            _constraint("component_keepout","keepout",{"part":"body","parts":["body","lid"],"inside_envelope":True,"size":[40,20,16],"center":[0,0,12],"max_volume":.001},["body_cavity"]),
        ]
        return DesignSpec.model_validate({"name":"Instrument enclosure","family":name,"parameters":params,"parts":[{"id":"body","name":"Enclosure body","feature":"body_edges","color":"#59beb8"},{"id":"lid","name":"Separate lid","feature":"lid_holes","color":"#d1dcda"}],"features":features,"constraints":constraints,"assumptions":["The 80 × 50 × 30 mm envelope includes the closed, separate 2 mm lid.","Mounting axes are fixed in the origin datum; all STEP/STL coordinates use millimeters."]})
    if name == "plate":
        params={"width":_parameter(100),"depth":_parameter(60),"thickness":_parameter(6),"hole_diameter":_parameter(5),"mount_x":_parameter(38),"mount_y":_parameter(20),"edge_chamfer":_parameter(.5)}
        centers=[["-mount_x","-mount_y",0],["mount_x","-mount_y",0],["mount_x","mount_y",0],["-mount_x","mount_y",0]]
        features=[_feature("plate_blank","box","plate",{"size":["width","depth","thickness"],"center":[0,0,"thickness/2"]}),_feature("mount_holes","hole","plate",{"centers":centers,"diameter":"hole_diameter","depth":"thickness+2*mm","start":-1,"axis":"Z"},["plate_blank"]),_feature("plate_pocket","pocket","plate",{"size":[28,20,2],"center":[0,0,"thickness-1*mm"]},["mount_holes"]),_feature("plate_edges","chamfer","plate",{"length":"edge_chamfer","selector":"outer_vertical"},["plate_pocket"])]
        return DesignSpec.model_validate({"name":"Mounting plate","family":name,"parameters":params,"parts":[{"id":"plate","name":"Mounting plate","feature":"plate_edges"}],"features":features,"constraints":[_constraint("envelope","envelope",{"size":["width","depth","thickness"]}),_constraint("mounting_pattern","hole_pattern",{"part":"plate","diameter":"hole_diameter","centers":centers,"axis":"Z","count":4},["mount_holes"]),_constraint("plate_floor","thickness",{"part":"plate","start":[0,0,-1],"direction":[0,0,1],"length":"thickness+2*mm","expected":"thickness-2*mm"},["plate_pocket"])]})
    if name == "bracket":
        params={"width":_parameter(60),"depth":_parameter(40),"height":_parameter(40),"thickness":_parameter(4),"hole_diameter":_parameter(5),"mount_x":_parameter(20),"fillet_radius":_parameter(.5)}
        centers=[["-mount_x",0,0],["mount_x",0,0]]
        features=[_feature("base","box","bracket",{"size":["width","depth","thickness"],"center":[0,0,"thickness/2"]}),_feature("flange","box","bracket",{"size":["width","thickness","height"],"center":[0,"-depth/2+thickness/2","height/2"]}),_feature("bracket_union","union","bracket",{},["base","flange"]),_feature("mount_holes","hole","bracket",{"centers":centers,"diameter":"hole_diameter","depth":"thickness+2*mm","start":-1,"axis":"Z"},["bracket_union"]),_feature("bracket_edges","fillet","bracket",{"radius":"fillet_radius","selector":"outer_vertical"},["mount_holes"])]
        return DesignSpec.model_validate({"name":"Orthogonal mounting bracket","family":name,"parameters":params,"parts":[{"id":"bracket","name":"Bracket","feature":"bracket_edges"}],"features":features,"constraints":[_constraint("envelope","envelope",{"size":["width","depth","height"]}),_constraint("mounting_pattern","hole_pattern",{"part":"bracket","diameter":"hole_diameter","centers":centers,"axis":"Z","count":2},["mount_holes"]),_constraint("base_thickness","thickness",{"part":"bracket","start":[0,0,-1],"direction":[0,0,1],"length":"height+2*mm","expected":"thickness"},["base"])]})
    raise ValueError(f"Unknown recipe {name!r}; choose enclosure, plate, or bracket")
