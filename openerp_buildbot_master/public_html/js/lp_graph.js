var monthtext = ['January','February','March','April','May','June',
                   'July','August','September','October','November','December'];
function populatedropdown(monthfrom, yearfrom, monthto, yearto){
    var today=new Date()
    
    var monthfrom=document.getElementById(monthfrom)
    var yearfrom=document.getElementById(yearfrom)
    var monthto=document.getElementById(monthto)
    var yearto=document.getElementById(yearto)
    
    for (var m=0; m<12; m++){
        monthfrom.options[m]=new Option(monthtext[m], monthtext[m]);
        monthfrom.options[today.getMonth()]=new Option(monthtext[today.getMonth()], monthtext[today.getMonth()]);
        monthto.options[m]=new Option(monthtext[m], monthtext[m]);
        monthto.options[today.getMonth()]=new Option(monthtext[today.getMonth()], monthtext[today.getMonth()], true, true)}
    var thisyear=today.getFullYear()
    for (var y=0; y<5; y++){
    yearfrom.options[y] = new Option(thisyear, thisyear)
    yearto.options[y] = new Option(thisyear, thisyear)
    thisyear-=1
    }
    yearfrom.options[0]=new Option(today.getFullYear(), today.getFullYear(), true, true)
    yearto.options[0]=new Option(today.getFullYear(), today.getFullYear(), true, true)
}

function getCurrBuilds()
{
    url = "one_box_per_builder"
    frame = document.getElementById('frame_lastbuild')
    frame.src=url;
    frame_doc=frame.contentWindow.document;
    lis = frame_doc.getElementsByTagName('table')
    curr_builds_table = document.getElementById('curr_builds_table')
    curr_builds_table.innerHTML = lis[2].innerHTML
   // populatedropdown("monthFrom", "yearFrom","monthTo","yearTo")
    getlatestgraph()
}

function GetGraphvalues() {
    url = "GetGraphvalues";
    frame = document.getElementById('frame_graph');
    frame.src=url;
    frame_doc=frame.contentWindow.document;
    datasets=frame_doc.getElementById('datasets').innerHTML;
    return eval(datasets)    
}   
             
function getlatestgraph() {
    //var monthfrom = document.getElementById("monthFrom")
    //var yearfrom = document.getElementById("yearFrom")
    //var monthto = document.getElementById("monthTo")
    //var yearto = document.getElementById("yearTo")
    //var monfrom = monthfrom.options[monthfrom.selectedIndex].value
    //var yrfrom = yearfrom.options[yearfrom.selectedIndex].value
    //var monto = monthto.options[monthto.selectedIndex].value
    //var yrto = yearto.options[yearto.selectedIndex].value
    //if  (yrto < yrfrom)
      //  alert('Please Enter the year correctly (From year < To year)')
    var data = GetGraphvalues()
    var newbug = []
    var inprogress = [] 
    var confirmed = [] 
    var fixreleased = []
    for (var i in data){  
        for (var j in data[i]){
            if ( i == 0){                                
              newbug.push([(new Date(data[i][j][0]+'/'+data[i][j][1]+'/01')).getTime(),data[i][j][2]]);}
            else if (i==1){
              confirmed.push([(new Date(data[i][j][0]+'/'+data[i][j][1]+'/01')).getTime(),data[i][j][2]]);}
            else if (i == 2){
              inprogress.push([(new Date(data[i][j][0]+'/'+data[i][j][1]+'/01')).getTime(),data[i][j][2]]);}
            else{
              fixreleased.push([(new Date(data[i][j][0]+'/'+data[i][j][1]+'/01')).getTime(),data[i][j][2]]);}
                       }      
                             }

    $.plot($("#placeholder"), 
       [ { data:newbug,     label: "New",         lines: { show: true, lineWidth: 1} },
         { data:inprogress, label: "In Progress", lines: {  show: true, lineWidth: 1}  },
         { data:confirmed,  label: "Confirmed",   lines: { show: true, lineWidth: 1} },
         { data:fixreleased,  label: "FixReleased",lines: { show: true, lineWidth: 1} },
        ],
       { 
       xaxis: { mode: "time",
                timeformat: "%b%y",
                minTickSize: [1, "month"],
                min: (new Date("2008/01/01")).getTime(),
                max: (new Date("2009/12/31")).getTime() 
               },
        yaxis:{ min:0 },
        shadowSize: 1,
        selection: { mode: "xy" },
        legend: {show: true, position: 'nw',noColumns: 3},
        grid: { hoverable: true, clickable: true ,  backgroundColor: "#fffaff"},
        points: { show: true },
        });
    function showTooltip(x, y, contents) {
        $('<div id="tooltip">' + contents + '</div>').css( {
            position: 'absolute',
            display: 'none',
            top: y + 5,
            left: x + 5,
            border: '1px solid #fdd',
            padding: '2px',
            'background-color': '#fee',
            opacity: 0.80
        }).appendTo("body").fadeIn(200);
    }

    var previousPoint = null;
    $("#placeholder").bind("plothover", function (event, pos, item) {
        $("#x").text(pos.x.toFixed(0));
        $("#y").text(pos.y.toFixed(0));

        if (item) {
            if (previousPoint != item.datapoint) {
                previousPoint = item.datapoint;
                
                $("#tooltip").remove();
                var x = item.datapoint[0],
                    y = item.datapoint[1];
                var dt = new Date(x)
                labelX = monthtext[dt.getMonth()] +" "+ dt.getFullYear()
                if (item.series.label == 'New')
                    showTooltip(item.pageX, item.pageY,
                          y + " " + item.series.label + " Bugs " + " in " + labelX);
                else
                    showTooltip(item.pageX, item.pageY,
                          y +" Bugs " + item.series.label+" in " + labelX);
            }
        }
        else {
            $("#tooltip").remove();
            previousPoint = null;            
        }
 });
}


