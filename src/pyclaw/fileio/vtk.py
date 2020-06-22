#!/usr/bin/python

# Author: Xinsheng (Shawn) Qin
# date: 03/2016
# Modified by Katy Barnhart
# date 05/2020

import sys
import os
import numpy as np
from clawpack.pyclaw import Solution
import vtk
from vtk.util import numpy_support

def write(
    solution,
    frame,
    path="_output",
    file_prefix='claw',
    write_aux=None,
    options=None,
    write_p=None,
    ):
    """Write out a VTK representation of solution

    For each input frame the following files and directories are created:
      - input_prefixXXXX.vthb. This file provides the metadata to describe
        how AMR patches are represented in the .vti files (including a relative
        path to the .vti files).
      - directory: input_prefixXXXX containing multiple files called
        input_prefixXXXX_<index>.vti. <index> represents the file index. There
        is a file for each patch at each AMR level.

    # the VTK users guide:
    https://www.kitware.com/products/books/VTKUsersGuide.pdf

    # these VTK classes
    https://vtk.org/doc/nightly/html/classvtkUniformGrid.html
    https://vtk.org/doc/nightly/html/classvtkOverlappingAMR.html
    https://vtk.org/doc/nightly/html/classvtkAMRBox.html
    https://vtk.org/doc/nightly/html/classvtkXMLUniformGridAMRWriter.html

    # These vtk examples.
    https://lorensen.github.io/VTKExamples/site/Python/CompositeData/OverlappingAMR/
    https://lorensen.github.io/VTKExamples/site/Python/IO/WriteXMLLinearCells/

    # blog post on numpy integration:
    https://blog.kitware.com/improved-vtk-numpy-integration-part-5/

    To open in paraview, choose the group of .vthb files, not the group of
    folders. This will be read in as cell data. In order to use filters like
    WarpByScalar you must use the CellDataToPointData filter first.

    :Input:
     - *solution* - (:class:`~pyclaw.solution.Solution`) Pyclaw object to be
       output
     - *frame* - (int) Frame number
     - *path* - (string) Root path
     - *file_prefix* - (string) Prefix for the file name. ``default = 'claw'``
     - *write_aux* - (bool) Not implemented.
     - *options* - (dict) Not implemented.
     - *write_p* - (bool) Not implemented.

    Note that some keyword arguments are not used. This is to maintain
    compatibility with the function signature expected by
    :py:class:`~pyclaw.Solution`

    Notes on what is not yet implemented
        - Add options for writing aux files.
        - Consider making an equilvalent vtk.read function.
    """
    assert(isinstance(frame, int))
    assert(isinstance(solution, Solution))
    _set_overlapped_status(solution)

    global_origin = solution.state.patch.lower_global + [0.]  # base patch
    levels = [state.patch.level-1 for state in solution.states]

    # shift base level to 0, since the base level in clawpack
    # is 1 while the base level in VTK is 0
    level_count = {}
    level_spacing = {}  # spacing of each level
    for i, level in enumerate(levels):
        if level in level_count.keys():
            level_count[level] = level_count[level] + 1
        else:
            level_count[level] = 1
            spacing = solution.states[i].patch.delta
            spacing.append(spacing[0])  # dz = dx
            spacing = np.array(spacing)
            level_spacing[level] = spacing
    numLevels = len(level_count.keys())

    # a list of num of patches at each level
    blocksPerLevel = [item[1] for item in
                     sorted(level_count.items(),
                            key=lambda a: a[0])]

    # Initialize the vtkOverlappingAMR object.
    amr = vtk.vtkOverlappingAMR()
    amr.Initialize(numLevels, blocksPerLevel)
    amr.SetOrigin(global_origin)

    # get states and initialize the global index (used below)
    states_sorted = sorted(solution.states, key=lambda a: a.patch.level)
    global_index = 0

    # for each AMR level create the vtkAMRBox and vtkUniformGrid and add to
    # the vtkOverlappingAMR object.
    for level in level_count.keys():
        # get number of blocks per level.
        nblocks = blocksPerLevel[level]

        # and the spacing at that level
        spacing = level_spacing[level]
        amr.SetSpacing(level, spacing)

        # for each block at this AMR level.
        for index in range(nblocks):

            # get the origin and number of dimensions.
            local_index = global_index + index

            origin = states_sorted[local_index].patch.lower_global + [0.]

            node_dims = [x + 1 for x in states_sorted[local_index].patch.num_cells_global + [0]]

            # create a vtkUniformGrid using the vtkAMRBox
            grid = vtk.vtkUniformGrid()
            grid.Initialize()
            grid.SetOrigin(origin)
            grid.SetSpacing(spacing)
            grid.SetDimensions(node_dims)

            # Set the data of the vtkUniformGrid

            # make AMR box
            # https://vtk.org/doc/nightly/html/classvtkAMRBox.html
            box = vtk.vtkAMRBox(origin, node_dims, spacing, global_origin)

                # Construct an AMR box from the description a vtkUniformGrid
            # Note that the dimensions specify the node dimensions, rather than the cell dimensions.
            # Nodes are one more than the cells.


            # get the cell data, and add each to the uniform grid.
            # ignore the last element of q, which provides info about overlapping.
            # it is set next.
            q = states_sorted[local_index].q

            for i in range(q.shape[0]-1):

                array_name = "q_"+str(i)
                q_i = q[i, ...]
                q_i = q_i.transpose()
                print(level, index, array_name, origin, spacing, node_dims, q_i.size, q_i.shape)

                #https://pyscience.wordpress.com/2014/09/06/numpy-to-vtk-converting-your-numpy-arrays-to-vtk-arrays-and-files/
                # transform into an array.
                array = numpy_support.numpy_to_vtk(num_array=q_i.ravel(), deep=True, array_type=vtk.VTK_FLOAT)

                # set the name.
                array.SetName(array_name)

                # verify the sizes are correct.
                assert q_i.size == grid.GetNumberOfCells()
                # add the array to the uniform grid.
                grid.GetCellData().AddArray(array)

            # mark overlapping cells using the vtkGhostType array name.
            q_ol = q[-1, ...]  # last piece is used to mark overlapped cells
            q_ol = q_ol.transpose()
            #amrbox.set_cell_data(q_ol, "vtkGhostType", "UInt8")
            array = numpy_support.numpy_to_vtk(q_ol.ravel(), deep=True, array_type=vtk.VTK_UNSIGNED_CHAR)
            array.SetName("vtkGhostType")
            # add the array to the uniform grid.
            grid.GetCellData().AddArray(array)

            # add AMR box and uniform grid to the overlapping AMR object.
            amr.SetAMRBox(level, index, box)
            amr.SetDataSet(level, index, grid)

            assert not box.IsInvalid()

        # after each level is done increment index
        global_index += nblocks

    # write out the vtkOverlappingAMR object.
    # https://lorensen.github.io/VTKExamples/site/Python/IO/WriteXMLLinearCells/

# TODO set precision of writing out correctly (7?)

# provide an option of binary or ascii?
    out = os.path.join(path, file_prefix+str(frame).zfill(4)+'.vthb')
    writer = vtk.vtkXMLUniformGridAMRWriter()
    writer.SetDataModeToAscii()
    writer.SetFileName(out)
    writer.SetInputData(amr)
    success = writer.Write()

    # assert writing returned 1, indicating success.
    assert success == 1

    # Potential future reference info on working with VTK.
    #https://stackoverflow.com/questions/7666981/how-to-set-data-values-on-a-vtkstructuredgrid/7667417#7667417

def _set_overlapped_status(sol):
    """
    return a list, overlapped_states,
    whose entries denote overlapped status for each patch.

    @type sol:  pyclaw.Solution
    @param sol: Solution obejct of pyclaw that contains all information
                of this time step.
    @rtype:     list
    @return:    add a component to the solution q,
                which contains overlapped status of each patch

    @type level_count:       dictionary
    @variable level_count:   a dictionary that maps levels
                             to number of patches of certain levels
                             e.g. {0:1, 1:2, 2:12}
    @type num_levels:        int
    @variable num_levels:    number of levels in total
    @type box_per_level:     list
    @variable box_per_level: [number of patches on level 0,
                              number of patches on level1, ...]

    """
    levels = [state.patch.level-1 for state in sol.states]
    # shift base level to 0
    level_count = {}
    level_spacing = {}  # spacing of each level
    for i, level in enumerate(levels):
        if level in level_count.keys():
            level_count[level] = level_count[level] + 1
        else:
            level_count[level] = 1
            spacing = sol.states[i].patch.delta
            spacing.append(spacing[0])  # dz = dx
            spacing = np.array(spacing)
            level_spacing[level] = spacing

    # a list of num of patches at each level
    box_per_level = [item[1] for item in
                     sorted(level_count.items(),
                            key=lambda a: a[0])]
    box_per_level = np.array(box_per_level)

    for state in sol.states:
        level = state.patch.level-1
        xlower_coarse = state.patch.dimensions[0].lower
        # xupper_coarse = state.patch.dimensions[0].upper
        ylower_coarse = state.patch.dimensions[1].lower
        # yupper_coarse = state.patch.dimensions[1].upper
        dx = state.patch.delta[0]
        dy = state.patch.delta[1]
        nx = state.patch.num_cells_global[0]
        ny = state.patch.num_cells_global[1]
        # in overlapped_status, entry with value 0 denotes
        # that the cell is not overlapped
        # entry with value 8 denotes that the cell is overlapped
        overlapped_status = np.zeros((1, state.q.shape[1], state.q.shape[2]))
        # convert from Fortran-Style to C-style
        # overlapped_status = overlapped_status.transpose(0, 2, 1)
        # In the future, efficiency of this part can be improved
        # by mapping grid levels to
        # a list of states of corresponding levels.
        # Otherwise, we need to scan each states in each outer loop as below
        for state_fine in sol.states:
            # find states with grid level of one higher
            if ((state_fine.patch.level-1) == level + 1):
                xlower_fine = state_fine.patch.dimensions[0].lower
                xupper_fine = state_fine.patch.dimensions[0].upper
                ylower_fine = state_fine.patch.dimensions[1].lower
                yupper_fine = state_fine.patch.dimensions[1].upper
                x_idx_lower = \
                    max(int(round((xlower_fine - xlower_coarse) /
                            float(dx))), 0)
                x_idx_upper = \
                    min(int(round((xupper_fine-xlower_fine)/dx)) +
                        x_idx_lower, nx)
                y_idx_lower = \
                    max(int(round((ylower_fine - ylower_coarse) /
                            float(dy))), 0)
                y_idx_upper = \
                    min(int(round((yupper_fine-ylower_fine)/dy)) +
                        y_idx_lower, ny)
                # set these cells to 8
                overlapped_status[0, x_idx_lower:x_idx_upper,
                                  y_idx_lower:y_idx_upper].fill(8)

            else:
                continue
        # state.q is in fortran style
        # state.q = np.vstack((state.q, overlapped_status.transpose(0, 2, 1)))
        state.q = np.vstack((state.q, overlapped_status))
